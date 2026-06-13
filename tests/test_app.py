import os
import io
import unittest
from unittest.mock import patch

import app as application


class FakeWorksheet:
    def __init__(self, title, values):
        self.title, self.values, self.appended = title, values, []

    def get_all_values(self): return self.values
    def batch_update(self, updates, value_input_option=None): self.updates = updates
    def append_row(self, row, value_input_option=None): self.appended.append(row); self.values.append(row)
    def clear(self): self.values = []
    def update(self, values, range_name=None, value_input_option=None):
        if range_name == "A1" or not self.values:
            self.values = values
        else:
            self.values[0].extend(values[0])
    def format(self, *args, **kwargs): pass
    def freeze(self, *args, **kwargs): pass


class FakeSpreadsheet:
    def __init__(self, worksheets): self.worksheets = worksheets
    def worksheet(self, name):
        if name not in self.worksheets: raise application.gspread.WorksheetNotFound(name)
        return self.worksheets[name]
    def add_worksheet(self, title, rows, cols):
        self.worksheets[title] = FakeWorksheet(title, [])
        return self.worksheets[title]


class AppTest(unittest.TestCase):
    def setUp(self):
        os.environ["APP_SECRET_KEY"] = "test-secret"
        os.environ["PHOTO_UPLOAD_SCRIPT_URL"] = "https://script.google.com/test"
        os.environ["PHOTO_UPLOAD_SECRET"] = "photo-secret"
        self.master = FakeWorksheet("MASTER_ASET", [application.MASTER_HEADERS, ["AST-0001", "LAPTOP", "LT-01", "BUDI", "DONE", "OK", "KANTOR", "AREA A", "", "", "", ""]])
        self.log = FakeWorksheet("LOG_OPNAME", [application.LOG_HEADERS])
        self.role = FakeWorksheet("ROLE", [
            application.ROLE_HEADERS,
            ["ADMIN", "1001", " SUPER ADMIN ", " all ", ""],
            ["ADMIN PIC", "1002", "SUPER ADMIN, PIC ASET", "ALL", "AREA A"],
            ["PIC MULTI", "1003", "PIC ASET", "AREA B, AREA A", ""],
            ["INVALID", "1004", "ADMIN", "ALL", ""],
            ["PIC EMPTY", "1005", "PIC ASET", "AREA Z", ""],
        ])
        self.dashboard = FakeWorksheet("DASHBOARD", [application.DASHBOARD_HEADERS])
        self.sheets = {"MASTER_ASET": self.master, "LOG_OPNAME": self.log, "ROLE": self.role, "DASHBOARD": self.dashboard}
        self.client = application.app.test_client()

    def worksheet(self, name): return self.sheets[name]

    def login(self, name="ADMIN PIC", user_id="1002"):
        response = self.client.post("/api/login", json={"name": name, "userId": user_id})
        return response, {"Authorization": "Bearer " + response.json["token"]} if response.status_code == 200 else {}

    @patch("app.get_worksheet")
    def test_login_normalization_validation_and_area_error(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        response, _ = self.login(" admin ", " 1001 ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["user"]["role"], "SUPER ADMIN")
        self.assertEqual(response.json["user"]["area"], "ALL")
        self.assertEqual(self.login("INVALID", "1004")[0].status_code, 403)
        self.assertEqual(self.login("ADMIN", "WRONG")[0].status_code, 401)

    @patch("app.get_worksheet")
    def test_submit_log_dashboard_and_score_rules(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        response = self.client.post("/api/opname", headers=headers, json={"assetCode": "AST-0001", "condition": "BAIK", "notes": "Sesuai"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.log.appended[0]), len(application.LOG_HEADERS))
        self.assertEqual(self.log.appended[0][-3:], ["ADMIN PIC", "1002", "SUPER ADMIN, PIC ASET"])
        self.assertEqual(response.json["summary"], {"total": 1, "completed": 1, "pending": 0, "good": 1, "damaged": 0})
        admin_score = next(item for item in response.json["scoreCard"] if item["name"] == "ADMIN PIC")
        self.assertEqual(admin_score["progress"], 100)
        self.assertEqual(admin_score["completed"], 1)
        self.assertEqual(admin_score["status"], "Selesai")

        second = self.client.post("/api/opname", headers=headers, json={"assetCode": "AST-0001", "condition": "RUSAK", "notes": "Perlu perbaikan"})
        self.assertEqual(second.json["summary"], {"total": 1, "completed": 1, "pending": 0, "good": 0, "damaged": 1})
        admin_score = next(item for item in second.json["scoreCard"] if item["name"] == "ADMIN PIC")
        self.assertEqual(admin_score["completed"], 1)
        self.assertEqual(admin_score["progress"], 100)

        self.log.values = [application.LOG_HEADERS]
        dashboard = self.client.get("/api/dashboard", headers=headers).json
        self.assertEqual(dashboard["summary"], {"total": 1, "completed": 0, "pending": 1, "good": 0, "damaged": 0})
        self.assertTrue(all(item["progress"] == 0 for item in dashboard["scoreCard"]))

    @patch("app.get_worksheet")
    def test_pure_super_admin_excluded_from_score(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login("ADMIN", "1001")
        self.client.post("/api/opname", headers=headers, json={"assetCode": "AST-0001", "condition": "RUSAK", "notes": ""})
        dashboard = self.client.get("/api/dashboard", headers=headers).json
        self.assertEqual(dashboard["summary"]["damaged"], 1)
        self.assertFalse(any(item["name"] == "ADMIN" for item in dashboard["scoreCard"]))

    @patch("app.get_worksheet")
    def test_pic_without_matching_area_rejected(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        response, _ = self.login("PIC EMPTY", "1005")
        self.assertEqual(response.status_code, 403)
        self.assertIn("tidak memiliki aset", response.json["message"])

    @patch("app.get_worksheet")
    def test_multi_area_access_and_scorecard_fallback(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        response, headers = self.login("PIC MULTI", "1003")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["user"]["areas"], ["AREA A", "AREA B"])
        dashboard = self.client.get("/api/dashboard", headers=headers).json
        score = next(item for item in dashboard["scoreCard"] if item["name"] == "PIC MULTI")
        self.assertEqual(score["scoreAreas"], "AREA B, AREA A")
        self.assertEqual(score["total"], 1)
        self.assertEqual(score["progress"], 0)

    @patch("app.get_spreadsheet")
    def test_setup_appends_missing_headers_without_overwriting_data(self, get_spreadsheet):
        old_master = FakeWorksheet("MASTER_ASET", [["NOMOR ASSET", "TYPE"], ["AST-X", "MEJA"]])
        spreadsheet = FakeSpreadsheet({"MASTER_ASET": old_master})
        get_spreadsheet.return_value = spreadsheet
        os.environ["SETUP_TOKEN"] = "setup-secret"
        response = self.client.post("/api/setup", headers={"X-Setup-Token": "setup-secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_master.values[1], ["AST-X", "MEJA"])
        self.assertTrue(all(header in old_master.values[0] for header in application.MASTER_HEADERS))

    def test_append_record_follows_actual_header_order(self):
        headers = ["TYPE", "NOMOR ASSET", *[h for h in application.LOG_HEADERS if h not in {"TYPE", "NOMOR ASSET"}]]
        sheet = FakeWorksheet("LOG_OPNAME", [headers])
        record = {header: header + "-VALUE" for header in application.LOG_HEADERS}
        application.append_record(sheet, "LOG_OPNAME", application.LOG_HEADERS, record)
        self.assertEqual(sheet.appended[0][0], "TYPE-VALUE")
        self.assertEqual(sheet.appended[0][1], "NOMOR ASSET-VALUE")

    @patch("app.call_photo_upload_script", return_value={"url": "https://drive.google.com/file/d/FILE-ID/view", "period": "2026-Jan-Jun"})
    @patch("app.get_worksheet")
    def test_upload_documentation_uses_apps_script_relay(self, get_worksheet, relay):
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        response = self.client.post(
            "/api/upload-documentation",
            headers=headers,
            data={"assetCode": "AST-0001", "photo": (io.BytesIO(b"photo"), "asset.jpg", "image/jpeg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("drive.google.com", response.json["url"])
        relay.assert_called_once()
        self.assertEqual(relay.call_args.args[0]["action"], "upload")
        self.assertTrue(relay.call_args.args[0]["base64Data"])

    @patch("app.call_photo_upload_script", return_value={"cleanup": {"keptPeriods": ["2026-Jan-Jun"], "trashedFolders": []}})
    def test_cleanup_admin_endpoint_uses_apps_script(self, relay):
        os.environ["SETUP_TOKEN"] = "setup-secret"
        response = self.client.get("/api/cleanup-drive-photos?token=setup-secret")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["cleanup"]["keptPeriods"], ["2026-Jan-Jun"])
        relay.assert_called_once_with({"action": "cleanup"})

    @patch("app.call_photo_upload_script", return_value={"message": "Tes berhasil", "testFileMovedToTrash": True})
    def test_photo_upload_admin_endpoint(self, relay):
        os.environ["SETUP_TOKEN"] = "setup-secret"
        response = self.client.get("/api/test-photo-upload?token=setup-secret")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["testFileMovedToTrash"])
        self.assertEqual(relay.call_args.args[0]["action"], "test")

    @patch("app.get_worksheet")
    def test_empty_photo_is_allowed(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        response = self.client.post("/api/upload-documentation", headers=headers, data={"assetCode": "AST-0001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["url"], "")

    def test_unknown_endpoint_returns_clean_json_404(self):
        response = self.client.get("/not-a-real-endpoint")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json["path"], "/not-a-real-endpoint")

    @patch("app.get_worksheet")
    def test_total_assets_survives_incomplete_log_headers(self, get_worksheet):
        self.log.values = [["TIMESTAMP", "NOMOR ASSET"]]
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        response = self.client.get("/api/dashboard", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["summary"]["total"], 1)
        self.assertEqual(response.json["summary"]["pending"], 1)
        self.assertTrue(response.json["warnings"])

    @patch("app.get_worksheet")
    def test_dashboard_period_filter(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        self.log.values.append(["2026-01-15 10:00:00", "AST-0001", "LAPTOP", "LT-01", "BUDI", "DONE", "OK", "KANTOR", "AREA A", "BAIK", "SUDAH OPNAME", "2026-01-15 10:00:00", "", "ADMIN PIC", "1002", "SUPER ADMIN, PIC ASET"])
        january = self.client.get("/api/dashboard?startDate=2026-01-01&endDate=2026-01-31", headers=headers).json
        february = self.client.get("/api/dashboard?startDate=2026-02-01&endDate=2026-02-28", headers=headers).json
        self.assertEqual(january["summary"]["total"], 1)
        self.assertEqual(january["summary"]["completed"], 1)
        self.assertEqual(february["summary"]["total"], 1)
        self.assertEqual(february["summary"]["completed"], 0)

    @patch("app.get_worksheet")
    def test_scorecard_period_and_information_counts(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        self.log.values.append([
            "2026-01-15 10:00:00", "AST-0001", "LAPTOP", "LT-01", "BUDI", "DONE", "OK", "KANTOR",
            "AREA A", "BAIK", "SUDAH OPNAME", "2026-01-15 10:00:00", "Lengkap",
            "https://drive.google.com/file/d/1/view", "ADMIN PIC", "1002", "SUPER ADMIN, PIC ASET"
        ])
        jan_jun = self.client.get("/api/dashboard?scorePeriod=JAN-JUN", headers=headers).json
        jul_des = self.client.get("/api/dashboard?scorePeriod=JUL-DES", headers=headers).json
        jan_score = next(item for item in jan_jun["scoreCard"] if item["name"] == "ADMIN PIC")
        jul_score = next(item for item in jul_des["scoreCard"] if item["name"] == "ADMIN PIC")
        self.assertEqual(jan_score["progress"], 100)
        self.assertEqual(jan_score["documentationCount"], 1)
        self.assertEqual(jan_score["notesCount"], 1)
        self.assertEqual(jan_score["good"], 1)
        self.assertEqual(jul_score["progress"], 0)

    @patch("app.get_worksheet")
    def test_asset_detail_still_loads_when_log_headers_incomplete(self, get_worksheet):
        self.log.values = [["TIMESTAMP", "NOMOR ASSET"]]
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        response = self.client.get("/api/assets/AST-0001", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["asset"]["assetCode"], "AST-0001")
        self.assertEqual(response.json["history"], [])
        self.assertTrue(response.json["warnings"])

    @patch("app.get_worksheet")
    def test_submit_repairs_log_then_updates_master_opname_and_condition(self, get_worksheet):
        self.log.values = [["TIMESTAMP", "NOMOR ASSET"], ["OLD", "AST-OLD"]]
        get_worksheet.side_effect = self.worksheet
        _, headers = self.login()
        response = self.client.post("/api/opname", headers=headers, json={"assetCode": "AST-0001", "condition": "RUSAK", "notes": "Roda rusak"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(header in self.log.values[0] for header in application.LOG_HEADERS))
        appended = dict(zip(self.log.values[0], self.log.appended[0]))
        self.assertEqual(appended["OPNAME"], "DONE")
        self.assertEqual(appended["KONDISI"], "RUSAK")
        self.assertEqual(appended["KONDISI TERAKHIR"], "RUSAK")
        master_updates = {item["range"]: item["values"][0][0] for item in self.master.updates}
        self.assertEqual(master_updates["E2"], "DONE")
        self.assertEqual(master_updates["F2"], "RUSAK")
        self.assertIn(application.current_period_status(), master_updates.values())


if __name__ == "__main__":
    unittest.main()
