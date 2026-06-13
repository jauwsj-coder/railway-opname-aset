import json
import os
import base64
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, time
from zoneinfo import ZoneInfo

import gspread
from flask import Flask, jsonify, render_template, request
from google.oauth2.service_account import Credentials
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


app = Flask(__name__)
MASTER_SHEET, LOG_SHEET, ROLE_SHEET, DASHBOARD_SHEET = "MASTER_ASET", "LOG_OPNAME", "ROLE", "DASHBOARD"
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Jakarta")
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
AUTH_MAX_AGE = 12 * 60 * 60

VALID_ROLES = {"SUPER ADMIN", "SUPER ADMIN, PIC ASET", "PIC ASET"}
PIC_ROLES = {"SUPER ADMIN, PIC ASET", "PIC ASET"}
GOOD_CONDITIONS = {"OK", "BAIK", "GOOD"}
DAMAGED_CONDITIONS = {"RUSAK", "BROKEN", "MAINTENANCE", "NOT OK"}

MASTER_HEADERS = ["NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "OPNAME", "KONDISI", "LOKASI DETAIL", "AREA", "KONDISI TERAKHIR", "STATUS TERAKHIR", "TANGGAL OPNAME TERAKHIR", "KETERANGAN TERAKHIR", "DOKUMENTASI TERAKHIR"]
LOG_HEADERS = ["TIMESTAMP", "NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "OPNAME", "KONDISI", "LOKASI DETAIL", "AREA", "KONDISI TERAKHIR", "STATUS TERAKHIR", "TANGGAL OPNAME TERAKHIR", "KETERANGAN TERAKHIR", "DOKUMENTASI TERAKHIR", "NAMA PETUGAS", "ID USER", "ROLE"]
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


@app.errorhandler(404)
def handle_not_found(error):
    return jsonify({"success": False, "message": "Endpoint tidak ditemukan.", "path": request.path}), 404


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
    user = find_role_user(payload.get("name"), payload.get("userId"))
    if not user:
        raise AppError("NAMA USER dan ID USER tidak cocok.", 401)
    identity = validated_identity(user)
    ensure_pic_has_assets(identity)
    return jsonify({"token": serializer().dumps(identity), "user": identity})


@app.get("/api/dashboard")
def dashboard():
    identity = require_user()
    start_date, end_date = parse_period(request.args.get("startDate"), request.args.get("endDate"))
    summary, score, warnings = build_dashboard(identity, start_date, end_date)
    return jsonify({"summary": summary, "scoreCard": score, "warnings": warnings, "scope": identity["area"]})


@app.post("/api/dashboard/sync")
def sync_dashboard():
    identity = require_user()
    if identity["role"] not in {"SUPER ADMIN", "SUPER ADMIN, PIC ASET"} or identity["area"] != "ALL":
        raise AppError("Hanya SUPER ADMIN dengan AREA ALL yang dapat melakukan Sync Sheet.", 403)
    summary, score, _ = build_dashboard(all_area_identity())
    write_dashboard_sheet(summary, score)
    return jsonify({"success": True, "message": "Sheet DASHBOARD berhasil diperbarui."})


@app.get("/api/assets/<asset_code>")
def find_asset(asset_code):
    identity = require_user()
    code = normalize(asset_code)
    if not code:
        raise AppError("NOMOR ASSET wajib diisi.")
    asset = next((row for row in get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS) if normalize(row["NOMOR ASSET"]) == code), None)
    if not asset:
        raise AppError(f"Aset {code} tidak ditemukan.", 404)
    ensure_area_access(identity, asset["AREA"])
    history, warnings = [], []
    try:
        history = [row for row in get_rows(get_worksheet(LOG_SHEET), LOG_HEADERS) if normalize(row["NOMOR ASSET"]) == code and can_access_area(identity, row["AREA"])]
        history.reverse()
    except AppError as error:
        warnings.append(f"Riwayat opname belum dapat ditampilkan: {error.message}")
    return jsonify({"asset": serialize_asset(asset), "history": [serialize_log(row) for row in history[:5]], "warnings": warnings})


@app.post("/api/opname")
def submit_opname():
    operator = require_user()
    payload = request.get_json(silent=True) or {}
    code, condition = normalize(payload.get("assetCode")), normalize(payload.get("condition"))
    notes, documentation = clean(payload.get("notes")), clean(payload.get("documentation"))
    if not code:
        raise AppError("NOMOR ASSET wajib diisi.")
    if condition not in GOOD_CONDITIONS | DAMAGED_CONDITIONS:
        raise AppError("KONDISI TERAKHIR harus OK/BAIK/GOOD atau RUSAK/BROKEN/MAINTENANCE/NOT OK.")

    master = get_worksheet(MASTER_SHEET)
    values = get_sheet_values(master, MASTER_SHEET)
    validate_headers(values, MASTER_HEADERS, MASTER_SHEET)
    headers = values[0]
    header_map = {header: index + 1 for index, header in enumerate(headers)}
    asset_row, asset = None, None
    for row_number, row_values in enumerate(values[1:], start=2):
        row = row_to_dict(headers, row_values)
        if normalize(row["NOMOR ASSET"]) == code:
            asset_row, asset = row_number, row
            break
    if not asset:
        raise AppError(f"Aset {code} tidak ditemukan.", 404)
    ensure_area_access(operator, asset["AREA"])

    date_value, status, opname_value = now_text(), current_period_status(), "DONE"
    log = get_worksheet(LOG_SHEET)
    ensure_required_headers(log, LOG_SHEET, LOG_HEADERS)
    append_record(log, LOG_SHEET, LOG_HEADERS, {
        "TIMESTAMP": date_value, "NOMOR ASSET": asset["NOMOR ASSET"], "TYPE": asset["TYPE"],
        "NO LAYOUT": asset["NO LAYOUT"], "USER": asset["USER"], "OPNAME": opname_value,
        "KONDISI": condition, "LOKASI DETAIL": asset["LOKASI DETAIL"], "AREA": asset["AREA"],
        "KONDISI TERAKHIR": condition, "STATUS TERAKHIR": status, "TANGGAL OPNAME TERAKHIR": date_value,
        "KETERANGAN TERAKHIR": notes, "NAMA PETUGAS": operator["name"], "ID USER": operator["userId"],
        "ROLE": operator["role"], "DOKUMENTASI TERAKHIR": documentation,
    })

    master.batch_update([
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["OPNAME"]), "values": [[opname_value]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["KONDISI"]), "values": [[condition]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["KONDISI TERAKHIR"]), "values": [[condition]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["STATUS TERAKHIR"]), "values": [[status]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["TANGGAL OPNAME TERAKHIR"]), "values": [[date_value]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["KETERANGAN TERAKHIR"]), "values": [[notes]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row, header_map["DOKUMENTASI TERAKHIR"]), "values": [[documentation]]},
    ], value_input_option="USER_ENTERED")

    summary, score, warnings = build_dashboard(operator)
    global_summary, global_score, _ = build_dashboard(all_area_identity())
    try:
        write_dashboard_sheet(global_summary, global_score)
    except AppError as error:
        warnings.append(f"Opname tersimpan, tetapi sheet DASHBOARD belum diperbarui: {error.message}")
    return jsonify({"success": True, "message": "Opname aset berhasil disimpan.", "summary": summary, "scoreCard": score, "warnings": warnings})


@app.post("/api/upload-documentation")
def upload_documentation():
    identity = require_user()
    file = request.files.get("photo")
    asset_code = normalize(request.form.get("assetCode"))
    if not file or not file.filename:
        return jsonify({"success": True, "url": "", "message": "Tidak ada foto yang diunggah."})
    if file.mimetype not in ALLOWED_IMAGE_TYPES:
        raise AppError("Format foto harus JPG, PNG, atau WEBP.")
    if not asset_code:
        raise AppError("NOMOR ASSET wajib diisi sebelum upload.")
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > 10 * 1024 * 1024:
        raise AppError("Ukuran foto maksimal 10 MB.")
    extension = os.path.splitext(file.filename)[1].lower() or ".jpg"
    name = f"{asset_code}_{datetime.now(ZoneInfo(TIMEZONE)).strftime('%Y%m%d_%H%M%S')}_{normalize(identity['userId'])}{extension}"
    result = call_photo_upload_script({
        "action": "upload",
        "fileName": name,
        "mimeType": file.mimetype,
        "base64Data": base64.b64encode(file.read()).decode("ascii"),
        "assetCode": asset_code,
    })
    return jsonify({"success": True, **result})


@app.get("/api/cleanup-drive-photos")
def cleanup_drive_photos_endpoint():
    expected_token = os.getenv("SETUP_TOKEN", "")
    if not expected_token or request.args.get("token", "") != expected_token:
        raise AppError("Setup token tidak valid.", 403)
    return jsonify({"success": True, **call_photo_upload_script({"action": "cleanup"})})


@app.get("/api/test-photo-upload")
def test_photo_upload_endpoint():
    expected_token = os.getenv("SETUP_TOKEN", "")
    if not expected_token or request.args.get("token", "") != expected_token:
        raise AppError("Setup token tidak valid.", 403)
    probe_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    result = call_photo_upload_script({
        "action": "test",
        "fileName": f"railway-upload-test-{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
        "mimeType": "image/png",
        "base64Data": probe_png,
    })
    return jsonify({"success": True, **result})


@app.post("/api/setup")
def setup_sheets():
    if request.headers.get("X-Setup-Token", "") != os.getenv("SETUP_TOKEN", "") or not os.getenv("SETUP_TOKEN"):
        raise AppError("Setup token tidak valid.", 403)
    spreadsheet = get_spreadsheet()
    results = [ensure_worksheet(spreadsheet, name, headers) for name, headers in (
        (MASTER_SHEET, MASTER_HEADERS), (LOG_SHEET, LOG_HEADERS), (ROLE_SHEET, ROLE_HEADERS), (DASHBOARD_SHEET, DASHBOARD_HEADERS)
    )]
    return jsonify({"success": True, "message": "Setup selesai tanpa menghapus data existing.", "sheets": results})


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
        token_identity = serializer().loads(header[7:], max_age=AUTH_MAX_AGE)
    except (BadSignature, SignatureExpired) as exc:
        raise AppError("Sesi sudah tidak valid. Silakan masuk kembali.", 401) from exc
    user = find_role_user(token_identity.get("name"), token_identity.get("userId"))
    if not user:
        raise AppError("User tidak lagi terdaftar pada sheet ROLE.", 401)
    identity = validated_identity(user)
    ensure_pic_has_assets(identity)
    return identity


def find_role_user(name, user_id):
    name_key, id_key = normalize(name), normalize(user_id)
    return next((row for row in get_rows(get_worksheet(ROLE_SHEET), ROLE_HEADERS) if normalize(row["NAMA USER"]) == name_key and normalize(row["ID USER"]) == id_key), None)


def validated_identity(row):
    role, area = normalize(row["ROLE"]), normalize(row["AREA"])
    if role not in VALID_ROLES:
        raise AppError(f"ROLE tidak valid: {clean(row['ROLE']) or '-'}", 403)
    if not area:
        raise AppError(f"AREA kosong untuk user {clean(row['NAMA USER']) or '-'}.", 403)
    return {"name": clean(row["NAMA USER"]), "userId": clean(row["ID USER"]), "role": role, "area": area}


def ensure_pic_has_assets(identity):
    if identity["role"] != "PIC ASET":
        return
    assets = get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS)
    if not any(normalize(row["NOMOR ASSET"]) and can_access_area(identity, row["AREA"]) for row in assets):
        raise AppError(f"PIC ASET tidak memiliki aset sesuai AREA {identity['area']}.", 403)


def build_dashboard(identity, start_date=None, end_date=None):
    master_rows = get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS)
    blank_area_codes = [clean(row["NOMOR ASSET"]) for row in master_rows if normalize(row["NOMOR ASSET"]) and not normalize(row["AREA"])]
    if blank_area_codes:
        raise AppError(f"AREA kosong pada MASTER_ASET untuk NOMOR ASSET: {', '.join(blank_area_codes[:5])}.", 503)
    assets = [row for row in master_rows if normalize(row["NOMOR ASSET"]) and can_access_area(identity, row["AREA"])]
    warnings = []
    try:
        logs = [row for row in get_rows(get_worksheet(LOG_SHEET), LOG_HEADERS) if normalize(row["NOMOR ASSET"]) and can_access_area(identity, row["AREA"]) and log_in_period(row, start_date, end_date)]
    except AppError as error:
        logs = []
        warnings.append(f"Data opname belum dapat dihitung: {error.message}")
    asset_codes = {normalize(row["NOMOR ASSET"]) for row in assets}
    scoped_logs = [row for row in logs if normalize(row["NOMOR ASSET"]) in asset_codes]
    latest_by_asset = {}
    for row in scoped_logs:
        latest_by_asset[normalize(row["NOMOR ASSET"])] = row
    completed = len(latest_by_asset)
    good = sum(1 for row in latest_by_asset.values() if log_condition(row) in GOOD_CONDITIONS)
    damaged = sum(1 for row in latest_by_asset.values() if log_condition(row) in DAMAGED_CONDITIONS)
    summary = {"total": len(assets), "completed": completed, "pending": max(len(assets) - completed, 0), "good": good, "damaged": damaged}

    pic_logs = [row for row in scoped_logs if normalize(row["ROLE"]) in PIC_ROLES]
    counts = Counter(normalize(row["ROLE"]) for row in pic_logs)
    total_pic_logs = sum(counts.values())
    score = [{"role": role, "count": count, "percentage": round(count * 100 / total_pic_logs, 2) if total_pic_logs else 0} for role, count in counts.most_common()]
    return summary, score, warnings


def parse_period(start_value, end_value):
    try:
        start_date = datetime.combine(datetime.strptime(start_value, "%Y-%m-%d").date(), time.min, ZoneInfo(TIMEZONE)) if start_value else None
        end_date = datetime.combine(datetime.strptime(end_value, "%Y-%m-%d").date(), time.max, ZoneInfo(TIMEZONE)) if end_value else None
    except ValueError as exc:
        raise AppError("Format periode tanggal tidak valid. Gunakan YYYY-MM-DD.") from exc
    if start_date and end_date and start_date > end_date:
        raise AppError("Tanggal awal tidak boleh lebih besar dari tanggal akhir.")
    return start_date, end_date


def log_in_period(row, start_date, end_date):
    if not start_date and not end_date:
        return True
    value = clean(row["TANGGAL OPNAME TERAKHIR"] or row["TIMESTAMP"])
    try:
        log_date = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo(TIMEZONE))
    except ValueError:
        return False
    return (not start_date or log_date >= start_date) and (not end_date or log_date <= end_date)


def log_condition(row):
    return normalize(row["KONDISI TERAKHIR"] or row["KONDISI"])


def can_access_all(identity):
    return identity["area"] == "ALL"


def all_area_identity():
    return {"role": "SUPER ADMIN", "area": "ALL"}


def can_access_area(identity, asset_area):
    return can_access_all(identity) or normalize(asset_area) == identity["area"]


def ensure_area_access(identity, asset_area):
    if not clean(asset_area):
        raise AppError("AREA aset kosong pada MASTER_ASET.", 403)
    if not can_access_area(identity, asset_area):
        raise AppError(f"Anda tidak memiliki akses untuk memproses aset AREA {clean(asset_area)}.", 403)


def write_dashboard_sheet(summary, score):
    sheet = get_worksheet(DASHBOARD_SHEET)
    updated = now_text()
    values = [DASHBOARD_HEADERS, ["TOTAL ASSET", summary["total"], updated], ["SUDAH OPNAME", summary["completed"], updated], ["BELUM OPNAME", summary["pending"], updated], ["ASET BAIK", summary["good"], updated], ["ASET RUSAK", summary["damaged"], updated], [], SCORE_HEADERS]
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
        return gspread.authorize(get_google_credentials()).open_by_key(spreadsheet_id)
    except json.JSONDecodeError as exc:
        raise AppError("GOOGLE_SERVICE_ACCOUNT_JSON bukan JSON yang valid.", 503) from exc
    except gspread.SpreadsheetNotFound as exc:
        raise AppError("Google Sheet tidak ditemukan atau service account belum memiliki akses.", 503) from exc
    except gspread.exceptions.APIError as exc:
        raise AppError("Google Sheet tidak bisa dibaca. Periksa API dan akses service account.", 503) from exc
    except (ValueError, KeyError) as exc:
        raise AppError("Kredensial service account tidak valid.", 503) from exc


def get_google_credentials():
    credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not credentials_json:
        raise AppError("GOOGLE_SERVICE_ACCOUNT_JSON belum dikonfigurasi.", 503)
    try:
        info = json.loads(credentials_json)
        return Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise AppError("Kredensial service account tidak valid.", 503) from exc


def call_photo_upload_script(payload):
    script_url = os.getenv("PHOTO_UPLOAD_SCRIPT_URL", "").strip()
    secret = os.getenv("PHOTO_UPLOAD_SECRET", "").strip()
    if not script_url:
        raise AppError("PHOTO_UPLOAD_SCRIPT_URL belum dikonfigurasi di Railway.", 503)
    if not secret:
        raise AppError("PHOTO_UPLOAD_SECRET belum dikonfigurasi di Railway.", 503)
    request_payload = {**payload, "secret": secret}
    relay_request = urllib.request.Request(
        script_url,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(relay_request, timeout=45) as response:
            raw_response = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"Apps Script upload relay mengembalikan HTTP {exc.code}. Detail: {detail[:500]}", 503) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"Apps Script upload relay tidak dapat dihubungi. Detail: {clean(exc.reason)}", 503) from exc
    except TimeoutError as exc:
        raise AppError("Apps Script upload relay timeout. Silakan coba kembali.", 504) from exc
    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise AppError(f"Respons Apps Script bukan JSON yang valid. Detail: {raw_response[:300]}", 503) from exc
    if not result.get("success"):
        raise AppError(f"Upload foto melalui Apps Script gagal. Detail: {clean(result.get('message')) or 'Tidak ada detail error.'}", 503)
    result.pop("success", None)
    return result


def get_worksheet(name):
    try:
        return get_spreadsheet().worksheet(name)
    except gspread.WorksheetNotFound as exc:
        raise AppError(f"Sheet {name} belum tersedia. Jalankan /api/setup.", 503) from exc
    except gspread.exceptions.APIError as exc:
        raise AppError(f"Sheet {name} tidak bisa dibaca. Periksa akses service account.", 503) from exc


def get_sheet_values(worksheet, sheet_name):
    try:
        return worksheet.get_all_values()
    except gspread.exceptions.APIError as exc:
        raise AppError(f"Sheet {sheet_name} tidak bisa dibaca. Periksa akses service account.", 503) from exc


def ensure_worksheet(spreadsheet, name, required_headers):
    try:
        worksheet = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=max(len(required_headers), 20))
    values = get_sheet_values(worksheet, name)
    existing_headers = values[0] if values else []
    missing = [header for header in required_headers if header not in existing_headers]
    if not existing_headers:
        worksheet.update([required_headers], "A1")
    elif missing:
        start_column = len(existing_headers) + 1
        worksheet.update([missing], gspread.utils.rowcol_to_a1(1, start_column))
    worksheet.freeze(rows=1)
    worksheet.format("1:1", {"backgroundColor": {"red": 1, "green": 1, "blue": 1}, "textFormat": {"bold": True, "foregroundColor": {"red": 0, "green": 0, "blue": 0}}})
    return {"name": name, "addedHeaders": missing}


def ensure_required_headers(worksheet, sheet_name, required_headers):
    values = get_sheet_values(worksheet, sheet_name)
    existing_headers = values[0] if values else []
    missing = [header for header in required_headers if header not in existing_headers]
    if not existing_headers:
        worksheet.update([required_headers], "A1")
    elif missing:
        worksheet.update([missing], gspread.utils.rowcol_to_a1(1, len(existing_headers) + 1))
    return missing


def get_rows(worksheet, expected_headers):
    values = get_sheet_values(worksheet, worksheet.title)
    validate_headers(values, expected_headers, worksheet.title)
    return [row_to_dict(values[0], row) for row in values[1:]]


def append_record(worksheet, sheet_name, required_headers, record):
    values = get_sheet_values(worksheet, sheet_name)
    validate_headers(values, required_headers, sheet_name)
    worksheet.append_row([record.get(header, "") for header in values[0]], value_input_option="USER_ENTERED")


def validate_headers(values, expected_headers, sheet_name):
    if not values:
        raise AppError(f"Header sheet {sheet_name} belum tersedia.", 503)
    missing = [header for header in expected_headers if header not in values[0]]
    if missing:
        raise AppError(f"Header sheet {sheet_name} belum lengkap: {', '.join(missing)}", 503)


def row_to_dict(headers, values):
    return dict(zip(headers, values + [""] * (len(headers) - len(values))))


def serialize_asset(row):
    return {"assetCode": clean(row["NOMOR ASSET"]), "type": clean(row["TYPE"]), "layoutNumber": clean(row["NO LAYOUT"]), "user": clean(row["USER"]), "opname": clean(row["OPNAME"]), "masterCondition": clean(row["KONDISI"]), "area": clean(row["AREA"]), "detailLocation": clean(row["LOKASI DETAIL"]), "lastCondition": clean(row["KONDISI TERAKHIR"]), "lastStatus": clean(row["STATUS TERAKHIR"]), "lastDate": clean(row["TANGGAL OPNAME TERAKHIR"]) or "-", "lastNotes": clean(row["KETERANGAN TERAKHIR"]), "lastDocumentation": clean(row["DOKUMENTASI TERAKHIR"])}


def serialize_log(row):
    return {"timestamp": clean(row["TIMESTAMP"]) or "-", "condition": clean(row["KONDISI TERAKHIR"] or row["KONDISI"]), "status": clean(row["STATUS TERAKHIR"]), "opnameDate": clean(row["TANGGAL OPNAME TERAKHIR"]) or "-", "notes": clean(row["KETERANGAN TERAKHIR"]), "documentation": clean(row["DOKUMENTASI TERAKHIR"]), "operator": clean(row["NAMA PETUGAS"]), "role": clean(row["ROLE"])}


def now_text():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


def current_period_status():
    month = datetime.now(ZoneInfo(TIMEZONE)).month
    return "SUDAH OPNAME JANUARI - JUNI" if month <= 6 else "SUDAH OPNAME JULI - DESEMBER"


def normalize(value):
    return clean(value).upper()


def clean(value):
    return "" if value is None else str(value).strip()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
