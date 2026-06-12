import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from flask import Flask, jsonify, render_template, request
from google.oauth2.service_account import Credentials


app = Flask(__name__)

MASTER_SHEET = "MASTER_ASET"
LOG_SHEET = "LOG_OPNAME"
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Jakarta")

MASTER_HEADERS = [
    "NOMOR ASSET",
    "TYPE",
    "NO LAYOUT",
    "USER",
    "OPNAME",
    "KONDISI",
    "LOKASI DETAIL",
    "KONDISI TERAKHIR",
    "STATUS TERAKHIR",
    "TANGGAL OPNAME TERAKHIR",
    "KETERANGAN TERAKHIR",
]

LOG_HEADERS = [
    "TIMESTAMP",
    "NOMOR ASSET",
    "TYPE",
    "NO LAYOUT",
    "USER",
    "KONDISI",
    "LOKASI DETAIL",
    "KONDISI HASIL OPNAME",
    "STATUS",
    "TANGGAL OPNAME",
    "DOKUMENTASI",
    "KETERANGAN",
]


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


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


@app.get("/api/dashboard")
def dashboard():
    rows = get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS)
    assets = [row for row in rows if normalize_code(row["NOMOR ASSET"])]
    summary = {"total": len(assets), "completed": 0, "pending": 0, "good": 0, "damaged": 0}

    for asset in assets:
        status = clean(asset["STATUS TERAKHIR"]).lower()
        condition = clean(asset["KONDISI TERAKHIR"]).lower()
        summary["completed" if status == "sudah opname" else "pending"] += 1
        if condition == "baik":
            summary["good"] += 1
        elif condition == "rusak":
            summary["damaged"] += 1

    return jsonify(summary)


@app.get("/api/assets/<asset_code>")
def find_asset(asset_code):
    code = normalize_code(asset_code)
    if not code:
        raise AppError("NOMOR ASSET wajib diisi.")

    master_rows = get_rows(get_worksheet(MASTER_SHEET), MASTER_HEADERS)
    asset = next((row for row in master_rows if normalize_code(row["NOMOR ASSET"]) == code), None)
    if not asset:
        raise AppError(f"Aset {code} tidak ditemukan.", 404)

    log_rows = get_rows(get_worksheet(LOG_SHEET), LOG_HEADERS)
    history = [row for row in log_rows if normalize_code(row["NOMOR ASSET"]) == code]
    history.reverse()

    return jsonify({"asset": serialize_asset(asset), "history": [serialize_log(row) for row in history[:5]]})


@app.post("/api/opname")
def submit_opname():
    payload = request.get_json(silent=True) or {}
    code = normalize_code(payload.get("assetCode"))
    condition = clean(payload.get("condition"))
    notes = clean(payload.get("notes"))
    documentation = clean(payload.get("documentation"))

    if not code:
        raise AppError("NOMOR ASSET wajib diisi.")
    if condition not in ("Baik", "Rusak"):
        raise AppError("Kondisi hasil opname tidak valid.")
    if documentation and not documentation.lower().startswith(("http://", "https://")):
        raise AppError("Dokumentasi harus berupa tautan http/https.")

    master = get_worksheet(MASTER_SHEET)
    master_values = master.get_all_values()
    validate_headers(master_values, MASTER_HEADERS, MASTER_SHEET)
    header_map = {header: index + 1 for index, header in enumerate(master_values[0])}

    asset_row_number = None
    asset = None
    for row_number, values in enumerate(master_values[1:], start=2):
        row = row_to_dict(master_values[0], values)
        if normalize_code(row["NOMOR ASSET"]) == code:
            asset_row_number = row_number
            asset = row
            break

    if not asset:
        raise AppError(f"Aset {code} tidak ditemukan.", 404)

    now = datetime.now(ZoneInfo(TIMEZONE))
    date_value = now.strftime("%Y-%m-%d %H:%M:%S")
    status = "Sudah Opname"

    updates = [
        {"range": gspread.utils.rowcol_to_a1(asset_row_number, header_map["KONDISI TERAKHIR"]), "values": [[condition]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row_number, header_map["STATUS TERAKHIR"]), "values": [[status]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row_number, header_map["TANGGAL OPNAME TERAKHIR"]), "values": [[date_value]]},
        {"range": gspread.utils.rowcol_to_a1(asset_row_number, header_map["KETERANGAN TERAKHIR"]), "values": [[notes]]},
    ]
    master.batch_update(updates, value_input_option="USER_ENTERED")

    log = get_worksheet(LOG_SHEET)
    validate_headers(log.get_all_values(), LOG_HEADERS, LOG_SHEET)
    log.append_row(
        [
            date_value,
            asset["NOMOR ASSET"],
            asset["TYPE"],
            asset["NO LAYOUT"],
            asset["USER"],
            asset["KONDISI"],
            asset["LOKASI DETAIL"],
            condition,
            status,
            date_value,
            documentation,
            notes,
        ],
        value_input_option="USER_ENTERED",
    )
    return jsonify({"success": True, "message": "Opname aset berhasil disimpan."})


@app.post("/api/setup")
def setup_sheets():
    expected_token = os.getenv("SETUP_TOKEN", "")
    supplied_token = request.headers.get("X-Setup-Token", "")
    if not expected_token or supplied_token != expected_token:
        raise AppError("Setup token tidak valid.", 403)

    spreadsheet = get_spreadsheet()
    ensure_worksheet(spreadsheet, MASTER_SHEET, MASTER_HEADERS)
    ensure_worksheet(spreadsheet, LOG_SHEET, LOG_HEADERS)
    return jsonify({"success": True, "message": "Header Google Sheets berhasil disiapkan."})


def get_spreadsheet():
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not spreadsheet_id or not credentials_json:
        raise AppError("Konfigurasi Google Sheets belum lengkap.", 503)

    try:
        service_account_info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise AppError("GOOGLE_SERVICE_ACCOUNT_JSON bukan JSON yang valid.", 503) from exc

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
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
    padded = values + [""] * (len(headers) - len(values))
    return dict(zip(headers, padded))


def serialize_asset(row):
    return {
        "assetCode": clean(row["NOMOR ASSET"]),
        "type": clean(row["TYPE"]),
        "layoutNumber": clean(row["NO LAYOUT"]),
        "user": clean(row["USER"]),
        "opname": clean(row["OPNAME"]),
        "masterCondition": clean(row["KONDISI"]),
        "detailLocation": clean(row["LOKASI DETAIL"]),
        "lastCondition": clean(row["KONDISI TERAKHIR"]),
        "lastStatus": clean(row["STATUS TERAKHIR"]),
        "lastDate": clean(row["TANGGAL OPNAME TERAKHIR"]) or "-",
        "lastNotes": clean(row["KETERANGAN TERAKHIR"]),
    }


def serialize_log(row):
    return {
        "timestamp": clean(row["TIMESTAMP"]) or "-",
        "condition": clean(row["KONDISI HASIL OPNAME"]),
        "status": clean(row["STATUS"]),
        "opnameDate": clean(row["TANGGAL OPNAME"]) or "-",
        "documentation": clean(row["DOKUMENTASI"]),
        "notes": clean(row["KETERANGAN"]),
    }


def normalize_code(value):
    return clean(value).upper()


def clean(value):
    return "" if value is None else str(value).strip()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
