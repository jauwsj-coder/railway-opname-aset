import os
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
    def update(self, values, range_name=None, value_input_option=None): self.values = values
    def format(self, *args, **kwargs): pass


class AppTest(unittest.TestCase):
    def setUp(self):
        os.environ["APP_SECRET_KEY"] = "test-secret"
        self.master = FakeWorksheet("MASTER_ASET", [application.MASTER_HEADERS, ["AST-0001", "LAPTOP", "LT-01", "BUDI", "YA", "AKTIF", "AREA A", "KANTOR", "", "", "", ""]])
        self.log = FakeWorksheet("LOG_OPNAME", [application.LOG_HEADERS])
        self.role = FakeWorksheet("ROLE", [application.ROLE_HEADERS, ["YOLANA", "ID-001", "PIC ASSET"]])
        self.dashboard = FakeWorksheet("DASHBOARD", [application.DASHBOARD_HEADERS])
        self.client = application.app.test_client()

    def worksheet(self, name):
        return {"MASTER_ASET": self.master, "LOG_OPNAME": self.log, "ROLE": self.role, "DASHBOARD": self.dashboard}[name]

    def login(self):
        response = self.client.post("/api/login", json={"name": "YOLANA", "userId": "ID-001"})
        return {"Authorization": "Bearer " + response.json["token"]}

    def test_health_page_and_login(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        with patch("app.get_worksheet", side_effect=self.worksheet):
            self.assertEqual(self.client.get("/api/users").status_code, 200)
            self.assertEqual(self.client.post("/api/login", json={"name": "YOLANA", "userId": "SALAH"}).status_code, 401)

    @patch("app.get_worksheet")
    def test_asset_submit_score_and_dashboard_sync(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        headers = self.login()
        self.assertEqual(self.client.get("/api/assets/AST-0001", headers=headers).status_code, 200)
        response = self.client.post("/api/opname", headers=headers, json={"assetCode": "AST-0001", "condition": "Baik", "documentation": "", "notes": "Sesuai"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.log.appended[0][-3:], ["YOLANA", "ID-001", "PIC ASSET"])
        self.assertEqual(response.json["scoreCard"][0]["role"], "PIC ASSET")
        self.assertEqual(self.client.post("/api/dashboard/sync", headers=headers).status_code, 200)
        self.assertEqual(self.dashboard.values[0], application.DASHBOARD_HEADERS)


if __name__ == "__main__":
    unittest.main()
