import unittest
from unittest.mock import patch

import app as application


class FakeWorksheet:
    def __init__(self, title, values):
        self.title = title
        self.values = values
        self.appended = []

    def get_all_values(self):
        return self.values

    def batch_update(self, updates, value_input_option=None):
        self.updates = updates

    def append_row(self, row, value_input_option=None):
        self.appended.append(row)


class AppTest(unittest.TestCase):
    def setUp(self):
        self.master = FakeWorksheet(
            "MASTER_ASET",
            [
                application.MASTER_HEADERS,
                ["AST-0001", "LAPTOP", "LT-01", "BUDI", "YA", "AKTIF", "KANTOR", "", "", "", ""],
            ],
        )
        self.log = FakeWorksheet("LOG_OPNAME", [application.LOG_HEADERS])
        self.client = application.app.test_client()

    def worksheet(self, name):
        return self.master if name == "MASTER_ASET" else self.log

    def test_health_and_page(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    @patch("app.get_worksheet")
    def test_asset_and_submit(self, get_worksheet):
        get_worksheet.side_effect = self.worksheet
        self.assertEqual(self.client.get("/api/assets/AST-0001").status_code, 200)
        response = self.client.post(
            "/api/opname",
            json={"assetCode": "AST-0001", "condition": "Baik", "documentation": "", "notes": "Sesuai"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.log.appended), 1)


if __name__ == "__main__":
    unittest.main()
