import json
import os
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from flask import Flask, jsonify, render_template, request
from google.oauth2.service_account import Credentials
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


app = Flask(__name__)
MASTER_SHEET, LOG_SHEET, ROLE_SHEET, DASHBOARD_SHEET = "MASTER_ASET", "LOG_OPNAME", "ROLE", "DASHBOARD"
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Jakarta")
AUTH_MAX_AGE = 12 * 60 * 60

MASTER_HEADERS = ["NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "OPNAME", "KONDISI", "AREA", "LOKASI DETAIL", "KONDISI TERAKHIR", "STATUS TERAKHIR", "TANGGAL OPNAME TERAKHIR", "KETERANGAN TERAKHIR"]
LOG_HEADERS = ["TIMESTAMP", "NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "KONDISI", "LOKASI DETAIL", "AREA", "KONDISI HASIL OPNAME", "STATUS", "TANGGAL OPNAME", "DOKUMENTASI", "KETERANGAN", "NAMA PETUGAS", "ID USER", "ROLE"]
ROLE_HEADERS = ["NAMA USER", "ID USER", "ROLE", "AREA"]
DASHBOARD_HEADERS = ["METRIK", "NILAI", "DIPERBARUI"]
SCORE_HEADERS = ["ROLE", "JUMLAH OPNAME", "PERSENTASE"]


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


@app.errorhandler(AppError)
def handle_app_error(error):
    return jsonify({"success": False, "message": error.message}), error.status


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception(error)
    return jsonify({"success": False, "message": "Terjadi kesalahan pada server."}), 500


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.get("/api/users")
def users():
    rows = get_rows(get_worksheet(ROLE_SHEET), ROLE_HEADERS)
    names = sorted({clean(row["NAMA USER"]) for row in rows if clean(row["NAMA USER"])})
    return jsonify({"users": names})


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    name, user_id = clean(payload.get("name")), clean(payload.get("userId"))
    user = find_role_user(name, user_id)
    if not user:
        raise AppError("Nama User atau ID User tidak sesuai.", 401)
    identity = {"name": user["NAMA USER"], "userId": user["ID USER"], "role": user["ROLE"], "area": user["AREA"]}
    return jsonify({"token": serializer().dumps(identity), "user": identity})


@app.get("/api/dashboard")
def dashboard():
    identity = require_user()
    summary, score = build_dashboard(identity)
    return jsonify({"summary": summary, "scoreCard": score})


@app.post("/api/dashboard/sync")
def sync_dashboard():
    identity = require_user()
    if not has_all_area_access(identity):
        raise AppError("Hanya SUPER ADMIN dengan AREA ALL yang dapat melakukan Sync Sheet.", 403)
    summary, score = build_dashboard(all_area_identity())
    write_dashboard_sheet(summary, score)
    return jsonify({"success": True, "message": "Sheet DASHBOARD berhasil diperbarui."})


@app.get("/api/assets/<asset_code>")
def find_asset(asset_code):
    identity = require_user()
    code = normalize_code(asset_code)
    if not code:
        raise AppError("NOMOR ASSET wajib diisi.")
    asset = next((row for row in get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS) if normalize_code(row["NOMOR ASSET"]) == code), None)
    if not asset:
        raise AppError(f"Aset {code} tidak ditemukan.", 404)
    ensure_area_access(identity, asset["AREA"])
    history = [row for row in get_rows(get_worksheet(LOG_SHEET), LOG_HEADERS) if normalize_code(row["NOMOR ASSET"]) == code]
    history.reverse()
    return jsonify({"asset": serialize_asset(asset), "history": [serialize_log(row) for row in history[:5]]})


@app.post("/api/opname")
def submit_opname():
    operator = require_user()
    payload = request.get_json(silent=True) or {}
    code, condition = normalize_code(payload.get("assetCode")), clean(payload.get("condition"))
    notes, documentation = clean(payload.get("notes")), clean(payload.get("documentation"))
    if not code:
        raise AppError("NOMOR ASSET wajib diisi.")
    if condition not in ("Baik", "Rusak"):
        raise AppError("Kondisi hasil opname tidak valid.")
    if documentation and not documentation.lower().startswith(("http://", "https://")):
        raise AppError("Dokumentasi harus berupa tautan http/https.")

    master = get_worksheet(MASTER_SHEET)
    values = master.get_all_values()
    validate_headers(values, MASTER_HEADERS, MASTER_SHEET)
    header_map = {header: index + 1 for index, header in enumerate(values[0])}
    asset_row, asset = None, None
    for row_number, row_values in enumerate(values[1:], start=2):
        row = row_to_dict(values[0], row_values)
        if normalize_code(row["NOMOR ASSET"]) == code:
            asset_row, asset = row_number, row
            break
    if not asset:
        raise AppError(f"Aset {code} tidak ditemukan.", 404)
    ensure_area_access(operator, asset["AREA"])

    date_value, status = now_text(), "Sudah Opname"
    updates = [
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["KONDISI TERAKHIR"]), "values": [[condition]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["STATUS TERAKHIR"]), "values": [[status]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["TANGGAL OPNAME TERAKHIR"]), "values": [[date_value]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["KETERANGAN TERAKHIR"]), "values": [[notes]]},
    ]
    master.batch_update(updates, value_input_option="USER_ENTERED")
    log = get_worksheet(LOG_SHEET)
    validate_headers(log.get_all_values(), LOG_HEADERS, LOG_SHEET)
    log.append_row([date_value, asset["NOMOR ASSET"], asset["TYPE"], asset["NO LAYOUT"], asset["USER"], asset["KONDISI"], asset["LOKASI DETAIL"], asset["AREA"], condition, status, date_value, documentation, notes, operator["name"], operator["userId"], operator["role"]], value_input_option="USER_ENTERED")
    summary, score = build_dashboard(operator)
    global_summary, global_score = build_dashboard(all_area_identity())
    write_dashboard_sheet(global_summary, global_score)
    return jsonify({"success": True, "message": "Opname aset berhasil disimpan.", "summary": summary, "scoreCard": score})


@app.post("/api/setup")
def setup_sheets():
    if request.headers.get("X-Setup-Token", "") != os.getenv("SETUP_TOKEN", "") or not os.getenv("SETUP_TOKEN"):
        raise AppError("Setup token tidak valid.", 403)
    spreadsheet = get_spreadsheet()
    for name, headers in ((MASTER_SHEET, MASTER_HEADERS), (LOG_SHEET, LOG_HEADERS), (ROLE_SHEET, ROLE_HEADERS), (DASHBOARD_SHEET, DASHBOARD_HEADERS)):
        ensure_worksheet(spreadsheet, name, headers)
    return jsonify({"success": True, "message": "Semua sheet berhasil disiapkan."})


def serializer():
    secret = os.getenv("APP_SECRET_KEY", "").strip()
    if not secret:
        raise AppError("APP_SECRET_KEY belum dikonfigurasi.", 503)
    return URLSafeTimedSerializer(secret, salt="opname-user")


def require_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AppError("Silakan masuk terlebih dahulu.", 401)
    try:
        identity = serializer().loads(header[7:], max_age=AUTH_MAX_AGE)
    except (BadSignature, SignatureExpired) as exc:
        raise AppError("Sesi sudah tidak valid. Silakan masuk kembali.", 401) from exc
    current_user = find_role_user(identity.get("name"), identity.get("userId"))
    if not current_user:
        raise AppError("User tidak lagi terdaftar pada sheet ROLE.", 401)
    return {"name": current_user["NAMA USER"], "userId": current_user["ID USER"], "role": current_user["ROLE"], "area": current_user["AREA"]}


def find_role_user(name, user_id):
    normalized_name, normalized_id = clean(name).casefold(), clean(user_id).casefold()
    return next((row for row in get_rows(get_worksheet(ROLE_SHEET), ROLE_HEADERS) if clean(row["NAMA USER"]).casefold() == normalized_name and clean(row["ID USER"]).casefold() == normalized_id), None)


def build_dashboard(identity):
    assets = [row for row in get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS) if normalize_code(row["NOMOR ASSET"]) and can_access_area(identity, row["AREA"])]
    summary = {"total": len(assets), "completed": 0, "pending": 0, "good": 0, "damaged": 0}
    for asset in assets:
        summary["completed" if clean(asset["STATUS TERAKHIR"]).lower() == "sudah opname" else "pending"] += 1
        condition = clean(asset["KONDISI TERAKHIR"]).lower()
        if condition == "baik": summary["good"] += 1
        elif condition == "rusak": summary["damaged"] += 1
    logs = [row for row in get_rows(get_worksheet(LOG_SHEET), LOG_HEADERS) if can_access_area(identity, row["AREA"])]
    counts = Counter(clean(row["ROLE"]) or "TANPA ROLE" for row in logs if clean(row["STATUS"]).lower() == "sudah opname")
    total_logs = sum(counts.values())
    score = [{"role": role, "count": count, "percentage": round(count * 100 / total_logs, 2) if total_logs else 0} for role, count in counts.most_common()]
    return summary, score


def is_super_admin(identity):
    roles = [part.strip().upper() for part in clean(identity.get("role")).split(",")]
    return "SUPER ADMIN" in roles


def has_all_area_access(identity):
    return is_super_admin(identity) and clean(identity.get("area")).upper() == "ALL"


def all_area_identity():
    return {"role": "SUPER ADMIN", "area": "ALL"}


def can_access_area(identity, asset_area):
    has_all_access = has_all_area_access(identity)
    same_area = clean(asset_area).casefold() == clean(identity.get("area")).casefold()
    return has_all_access or same_area


def ensure_area_access(identity, asset_area):
    if not can_access_area(identity, asset_area):
        raise AppError(f"Anda tidak memiliki akses untuk memproses aset AREA {clean(asset_area) or '-'}.", 403)


def write_dashboard_sheet(summary, score):
    sheet = get_worksheet(DASHBOARD_SHEET)
    updated = now_text()
    values = [DASHBOARD_HEADERS, ["TOTAL ASSET", summary["total"], updated], ["SUDAH OPNAME", summary["completed"], updated], ["BELUM OPNAME", summary["pending"], updated], ["ASSET BAIK", summary["good"], updated], ["ASSET RUSAK", summary["damaged"], updated], [], SCORE_HEADERS]
    values.extend([[item["role"], item["count"], item["percentage"] / 100] for item in score])
    sheet.clear()
    sheet.update(values, "A1", value_input_option="USER_ENTERED")
    if score:
        sheet.format(f"C9:C{8 + len(score)}", {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}})


def get_spreadsheet():
    spreadsheet_id, credentials_json = os.getenv("GOOGLE_SHEET_ID", "").strip(), os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not spreadsheet_id or not credentials_json:
        raise AppError("Konfigurasi Google Sheets belum lengkap.", 503)
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise AppError("GOOGLE_SERVICE_ACCOUNT_JSON bukan JSON yang valid.", 503) from exc
    credentials = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(credentials).open_by_key(spreadsheet_id)


def get_worksheet(name):
    try:
        return get_spreadsheet().worksheet(name)
    except gspread.WorksheetNotFound as exc:
        raise AppError(f"Sheet {name} belum tersedia. Jalankan setup terlebih dahulu.", 503) from exc


def ensure_worksheet(spreadsheet, name, headers):
    try:
        worksheet = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=max(len(headers), 20))
    worksheet.update([headers], "A1")
    worksheet.freeze(rows=1)
    worksheet.format("1:1", {"backgroundColor": {"red": 1, "green": 1, "blue": 1}, "textFormat": {"bold": True, "foregroundColor": {"red": 0, "green": 0, "blue": 0}}})


def get_rows(worksheet, expected_headers):
    values = worksheet.get_all_values()
    validate_headers(values, expected_headers, worksheet.title)
    return [row_to_dict(values[0], row) for row in values[1:]]


def validate_headers(values, expected_headers, sheet_name):
    if not values:
        raise AppError(f"Header sheet {sheet_name} belum tersedia.", 503)
    missing = [header for header in expected_headers if header not in values[0]]
    if missing:
        raise AppError(f"Header sheet {sheet_name} tidak lengkap: {', '.join(missing)}", 503)


def row_to_dict(headers, values):
    return dict(zip(headers, values + [""] * (len(headers) - len(values))))


def serialize_asset(row):
    return {"assetCode": clean(row["NOMOR ASSET"]), "type": clean(row["TYPE"]), "layoutNumber": clean(row["NO LAYOUT"]), "user": clean(row["USER"]), "opname": clean(row["OPNAME"]), "masterCondition": clean(row["KONDISI"]), "area": clean(row["AREA"]), "detailLocation": clean(row["LOKASI DETAIL"]), "lastCondition": clean(row["KONDISI TERAKHIR"]), "lastStatus": clean(row["STATUS TERAKHIR"]), "lastDate": clean(row["TANGGAL OPNAME TERAKHIR"]) or "-", "lastNotes": clean(row["KETERANGAN TERAKHIR"])}


def serialize_log(row):
    return {"timestamp": clean(row["TIMESTAMP"]) or "-", "condition": clean(row["KONDISI HASIL OPNAME"]), "status": clean(row["STATUS"]), "opnameDate": clean(row["TANGGAL OPNAME"]) or "-", "documentation": clean(row["DOKUMENTASI"]), "notes": clean(row["KETERANGAN"]), "operator": clean(row["NAMA PETUGAS"]), "role": clean(row["ROLE"])}


def now_text():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


def normalize_code(value):
    return clean(value).upper()


def clean(value):
    return "" if value is None else str(value).strip()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
