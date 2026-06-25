import importlib.util
import re
import tempfile
import unittest
from pathlib import Path


@unittest.skipIf(importlib.util.find_spec("flask") is None, "Flask is not installed in this environment")
class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        from app.config import Config
        from app import create_app

        self.tmp = tempfile.TemporaryDirectory()

        class TestConfig(Config):
            TESTING = True
            DATABASE_URL = f"sqlite:///{Path(self.tmp.name) / 'test.sqlite3'}"
            DATA_DIR = Path(self.tmp.name)
            UPLOAD_DIR = Path(self.tmp.name) / "uploads"

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, email="user@example.com", password="password"):
        svg = self.client.get("/api/auth/captcha").data.decode("utf-8")
        captcha = "".join(re.findall(r">([^<>])</text>", svg))
        return self.client.post("/api/auth/login", json={"account": email, "password": password, "captcha": captcha})

    def test_login_and_project_list(self):
        res = self.login()
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/projects")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.get_json()["total"], 4)

    def test_create_project(self):
        self.login()
        categories = self.client.get("/api/categories").get_json()["items"]
        statuses = self.client.get("/api/statuses").get_json()["items"]
        res = self.client.post(
            "/api/projects",
            json={
                "name": "接口测试项目",
                "folder": "测试目录/接口",
                "category_id": categories[0]["id"],
                "status_ids": [statuses[0]["id"], statuses[1]["id"]],
                "start_date": "2026-06-23",
                "next_node_date": "2026-06-24",
                "next_node": "接口测试下一步",
                "contract_amount": 100000,
                "invoiced_amount": 50000,
                "received_amount": 30000,
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("id", res.get_json())
        res = self.client.get("/api/projects?sort=amounts&direction=desc")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        amounts = [item["received_amount"] for item in data["items"]]
        self.assertEqual(amounts, sorted(amounts, reverse=True))
        created_category = next(row for row in data["category_amounts"] if row["category_id"] == categories[0]["id"])
        self.assertGreaterEqual(created_category["contract_amount"], 100000)
        self.assertGreaterEqual(created_category["invoiced_amount"], 50000)
        self.assertGreaterEqual(created_category["received_amount"], 30000)

    def test_admin_usage(self):
        res = self.login("admin", "Ad123654")
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/admin/users")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.get_json()["items"]), 2)


if __name__ == "__main__":
    unittest.main()
