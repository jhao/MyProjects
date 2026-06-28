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

    def test_personal_items_are_separated_from_projects(self):
        self.login()
        categories = self.client.get("/api/categories").get_json()["items"]
        res = self.client.post(
            "/api/projects",
            json={"item_type": "personal", "name": "个人事务测试", "folder": "个人/测试", "category_id": categories[0]["id"]},
        )
        self.assertEqual(res.status_code, 200)
        projects = self.client.get("/api/projects?item_type=project").get_json()
        personal = self.client.get("/api/projects?item_type=personal").get_json()
        self.assertFalse(any(item["name"] == "个人事务测试" for item in projects["items"]))
        self.assertTrue(any(item["name"] == "个人事务测试" for item in personal["items"]))
        item_id = res.get_json()["id"]
        log_res = self.client.post(f"/api/projects/{item_id}/logs", json={"log_date": "2026-06-25", "content": "事务日志内容"})
        self.assertEqual(log_res.status_code, 200)
        log_item = self.client.get(f"/api/projects/{item_id}/logs?date=2026-06-25").get_json()["item"]
        self.assertIn("事务日志", log_item["title"])

    def test_project_members_and_audit_logs(self):
        self.login("admin", "Ad123654")
        create_user = self.client.post("/api/admin/users", json={"email": "member@example.com", "nickname": "成员", "password": "password", "status": "active"})
        self.assertEqual(create_user.status_code, 200)
        self.client.post("/api/auth/logout")

        self.login()
        categories = self.client.get("/api/categories").get_json()["items"]
        users = self.client.get("/api/users/options").get_json()["items"]
        member = next(item for item in users if item["email"] == "member@example.com")
        res = self.client.post(
            "/api/projects",
            json={"name": "协作项目测试", "folder": "协作/测试", "category_id": categories[0]["id"], "member_ids": [member["id"]]},
        )
        self.assertEqual(res.status_code, 200)
        project_id = res.get_json()["id"]
        audit = self.client.get(f"/api/projects/{project_id}/audit-logs")
        self.assertEqual(audit.status_code, 200)
        self.assertTrue(any(item["action"] == "create" for item in audit.get_json()["items"]))

        self.client.post("/api/auth/logout")
        self.login("member@example.com", "password")
        visible = self.client.get("/api/projects?item_type=project").get_json()
        self.assertTrue(any(item["id"] == project_id for item in visible["items"]))

    def test_admin_usage(self):
        res = self.login("admin", "Ad123654")
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/admin/users")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.get_json()["items"]), 1)

    def test_change_own_password(self):
        self.login()
        wrong = self.client.post("/api/me/password", json={"old_password": "bad-password", "new_password": "newpass123", "confirm_password": "newpass123"})
        self.assertEqual(wrong.status_code, 400)

        changed = self.client.post("/api/me/password", json={"old_password": "password", "new_password": "newpass123", "confirm_password": "newpass123"})
        self.assertEqual(changed.status_code, 200)
        self.client.post("/api/auth/logout")

        old_login = self.login("user@example.com", "password")
        self.assertEqual(old_login.status_code, 400)
        new_login = self.login("user@example.com", "newpass123")
        self.assertEqual(new_login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
