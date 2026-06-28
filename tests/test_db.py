import tempfile
import unittest
from pathlib import Path

from app import db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_url = f"sqlite:///{Path(self.tmp.name) / 'test.sqlite3'}"
        db.init_db(self.db_url)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_users_and_passwords(self):
        admin = db.query_one("select * from users where email=?", ("admin",))
        user = db.query_one("select * from users where email=?", ("user@example.com",))
        self.assertEqual(admin["role"], "admin")
        self.assertEqual(user["nickname"], "张经理")
        self.assertTrue(db.verify_password("password", user["password_hash"]))
        self.assertFalse(db.verify_password("bad-password", user["password_hash"]))

    def test_existing_admin_password_is_not_reset_by_seed(self):
        admin = db.query_one("select * from users where email=?", ("admin",))
        db.execute("update users set password_hash=? where id=?", (db.hash_password("changed123"), admin["id"]))
        db.init_db(self.db_url)
        admin = db.query_one("select * from users where email=?", ("admin",))
        self.assertTrue(db.verify_password("changed123", admin["password_hash"]))
        self.assertFalse(db.verify_password("Ad123654", admin["password_hash"]))

    def test_default_workspace_seeded(self):
        user = db.query_one("select * from users where email=?", ("user@example.com",))
        categories = db.query_all("select * from categories where user_id=?", (user["id"],))
        statuses = db.query_all("select * from statuses where user_id=?", (user["id"],))
        projects = db.query_all("select * from projects where user_id=? and is_deleted=0", (user["id"],))
        self.assertGreaterEqual(len(categories), 4)
        self.assertGreaterEqual(len(statuses), 11)
        self.assertGreaterEqual(len(projects), 4)
        self.assertIn("contract_amount", projects[0])
        self.assertIn("invoiced_amount", projects[0])
        self.assertIn("received_amount", projects[0])

    def test_project_related_tables_work(self):
        project = db.query_one("select * from projects limit 1")
        milestone_count = db.query_one("select count(*) as c from milestones where project_id=?", (project["id"],))["c"]
        dir_count = db.query_one("select count(*) as c from document_dirs where project_id=?", (project["id"],))["c"]
        log_count = db.query_one("select count(*) as c from project_logs where project_id=?", (project["id"],))["c"]
        people_count = db.query_one("select count(*) as c from people where project_id=?", (project["id"],))["c"]
        self.assertGreaterEqual(milestone_count, 1)
        self.assertEqual(dir_count, 3)
        self.assertGreaterEqual(log_count, 1)
        self.assertGreaterEqual(people_count, 1)

    def test_create_user_and_project(self):
        uid = db.execute(
            "insert into users(email,nickname,password_hash,role,status,created_at,updated_at) values(?,?,?,?,?,?,?)",
            ("new@example.com", "新用户", db.hash_password("abc123"), "user", "active", db.now(), db.now()),
        )
        category_id = db.execute(
            "insert into categories(user_id,name,icon,color,sort_order,enabled) values(?,?,?,?,?,1)",
            (uid, "测试分类", "folder", "#2563eb", 0),
        )
        pid = db.execute(
            "insert into projects(user_id,name,folder,category_id,is_deleted,is_frozen,created_at,updated_at) values(?,?,?,?,0,0,?,?)",
            (uid, "测试项目", "测试目录", category_id, db.now(), db.now()),
        )
        project = db.query_one("select * from projects where id=?", (pid,))
        self.assertEqual(project["name"], "测试项目")
        self.assertEqual(project["received_amount"], 0)


if __name__ == "__main__":
    unittest.main()
