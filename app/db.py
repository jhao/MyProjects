import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .config import Config, is_mysql_url


_database_url = None


def _sqlite_path(database_url):
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise RuntimeError(f"Unsupported database URL for sqlite adapter: {database_url}")
    return parsed.path


def init_db(database_url):
    global _database_url
    _database_url = database_url
    Config.ensure_dirs()
    if is_mysql_url(database_url):
        raise RuntimeError("MySQL adapter placeholder is configured but not initialized. Use sqlite by default or implement mysql adapter in app/db.py.")
    db_path = Path(_sqlite_path(database_url))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        migrate_schema(conn)
        seed_defaults(conn)


def migrate_schema(conn):
    project_columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    amount_columns = {
        "contract_amount": "real not null default 0",
        "invoiced_amount": "real not null default 0",
        "received_amount": "real not null default 0",
        "item_type": "text not null default 'project'",
    }
    for name, definition in amount_columns.items():
        if name not in project_columns:
            conn.execute(f"alter table projects add column {name} {definition}")
    audit_columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()}
    if "details" not in audit_columns:
        conn.execute("alter table audit_logs add column details text")
    conn.execute(
        """create table if not exists project_members (
          project_id integer not null references projects(id) on delete cascade,
          user_id integer not null references users(id),
          can_edit integer not null default 1,
          created_at text not null,
          primary key(project_id,user_id)
        )"""
    )
    conn.execute("insert or ignore into project_members(project_id,user_id,can_edit,created_at) select id,user_id,1,created_at from projects where item_type='project'")


@contextmanager
def connect():
    if not _database_url:
        init_db(Config.DATABASE_URL)
    if is_mysql_url(_database_url):
        raise RuntimeError("MySQL runtime support requires installing PyMySQL and adding adapter methods in app/db.py.")
    conn = sqlite3.connect(_sqlite_path(_database_url))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now():
    return datetime.utcnow().replace(microsecond=0).isoformat()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 180000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, salt, _ = stored.split("$", 2)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def dict_row(row):
    return dict(row) if row else None


def query_all(sql, params=()):
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def query_one(sql, params=()):
    with connect() as conn:
        return dict_row(conn.execute(sql, params).fetchone())


def execute(sql, params=()):
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def seed_defaults(conn):
    admin_username = Config.ADMIN_USERNAME
    admin = conn.execute("select id from users where email=? and role='admin'", (admin_username,)).fetchone()
    if not admin:
        conn.execute(
            "insert into users(email,nickname,password_hash,role,status,created_at,updated_at) values(?,?,?,?,?,?,?)",
            (admin_username, "系统管理员", hash_password(Config.ADMIN_PASSWORD), "admin", "active", now(), now()),
        )
    else:
        conn.execute(
            "update users set nickname='系统管理员',status='active',updated_at=? where id=?",
            (now(), admin["id"]),
        )
    conn.execute("update users set status='frozen' where role='admin' and email<>?", (admin_username,))
    user = conn.execute("select id from users where email=?", ("user@example.com",)).fetchone()
    if not user:
        uid = conn.execute(
            "insert into users(email,nickname,password_hash,role,status,created_at,updated_at) values(?,?,?,?,?,?,?)",
            ("user@example.com", "张经理", hash_password("password"), "user", "active", now(), now()),
        ).lastrowid
        seed_user_workspace(conn, uid)
    else:
        ensure_user_defaults(conn, user["id"])
    for row in conn.execute("select id from users where role<>'admin'"):
        ensure_user_defaults(conn, row["id"])


def seed_user_workspace(conn, user_id):
    categories = [
        ("工程实施类", "building", "#2563eb"),
        ("贸易交易类", "briefcase", "#d97706"),
        ("创新探讨类", "spark", "#7c3aed"),
        ("办公事务类", "folder", "#475569"),
    ]
    status_items = [
        ("线索", "#2563eb", "business"),
        ("售前", "#7c3aed", "business"),
        ("未签合同", "#0f766e", "business"),
        ("招投标中", "#0891b2", "business"),
        ("合同", "#d97706", "business"),
        ("执行", "#16a34a", "business"),
        ("待验收", "#d97706", "business"),
        ("暂停", "#64748b", "control"),
        ("冻结", "#dc2626", "control"),
        ("完结", "#15803d", "control"),
        ("紧急", "#dc2626", "business"),
    ]
    for idx, item in enumerate(categories):
        ensure_category(conn, user_id, item[0], item[1], item[2], idx)
    for idx, item in enumerate(status_items):
        ensure_status(conn, user_id, item[0], item[1], item[2], idx)
    conn.execute(
        "insert into folder_templates(user_id,name,tree_json,is_default,created_at) values(?,?,?,?,?)",
        (user_id, "默认项目目录", '["01.项目启动","02.项目过程","03.项目完结"]', 1, now()),
    )
    cat_ids = {r["name"]: r["id"] for r in conn.execute("select id,name from categories where user_id=?", (user_id,))}
    status_ids = {r["name"]: r["id"] for r in conn.execute("select id,name from statuses where user_id=?", (user_id,))}
    samples = [
        ("滨海园区弱电改造", "重点客户/2026实施", "工程实施类", "2026-03-12", "2026-06-24", "提交施工变更确认单", ["执行", "紧急"]),
        ("进口备件贸易跟进", "贸易机会/机电备件", "贸易交易类", "2026-05-06", "2026-06-25", "核对付款条款", ["合同", "售前"]),
        ("AI 办公归档方案", "创新课题/办公效率", "创新探讨类", "2026-04-18", "2026-06-26", "完成演示脚本", ["线索", "执行"]),
        ("年度办公室搬迁准备", "办公事务/行政", "办公事务类", "2026-06-01", "2026-06-27", "资产清单复核", ["待验收"]),
    ]
    sample_amounts = {
        "滨海园区弱电改造": (1280000, 780000, 520000),
        "进口备件贸易跟进": (460000, 210000, 120000),
        "AI 办公归档方案": (180000, 0, 0),
        "年度办公室搬迁准备": (96000, 48000, 48000),
    }
    for name, folder, cat, start, next_date, next_node, sts in samples:
        contract_amount, invoiced_amount, received_amount = sample_amounts.get(name, (0, 0, 0))
        pid = conn.execute(
            """insert into projects(user_id,name,folder,category_id,start_date,next_node_date,next_node,description,
               contract_amount,invoiced_amount,received_amount,is_frozen,is_deleted,created_at,updated_at)
               values(?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)""",
            (user_id, name, folder, cat_ids[cat], start, next_date, next_node, "初始化示例项目", contract_amount, invoiced_amount, received_amount, now(), now()),
        ).lastrowid
        conn.execute("insert or ignore into project_members(project_id,user_id,can_edit,created_at) values(?,?,1,?)", (pid, user_id, now()))
        for st in sts:
            conn.execute("insert into project_statuses(project_id,status_id) values(?,?)", (pid, status_ids[st]))
        create_default_project_children(conn, pid)


def default_categories():
    return [
        ("工程实施类", "building", "#2563eb"),
        ("贸易交易类", "briefcase", "#d97706"),
        ("创新探讨类", "spark", "#7c3aed"),
        ("办公事务类", "folder", "#475569"),
    ]


def default_statuses():
    return [
        ("线索", "#2563eb", "business"),
        ("售前", "#7c3aed", "business"),
        ("未签合同", "#0f766e", "business"),
        ("招投标中", "#0891b2", "business"),
        ("合同", "#d97706", "business"),
        ("执行", "#16a34a", "business"),
        ("待验收", "#d97706", "business"),
        ("暂停", "#64748b", "control"),
        ("冻结", "#dc2626", "control"),
        ("完结", "#15803d", "control"),
        ("紧急", "#dc2626", "business"),
    ]


def ensure_category(conn, user_id, name, icon, color, sort_order):
    row = conn.execute("select id from categories where user_id=? and name=?", (user_id, name)).fetchone()
    if not row:
        conn.execute(
            "insert into categories(user_id,name,icon,color,sort_order,enabled) values(?,?,?,?,?,1)",
            (user_id, name, icon, color, sort_order),
        )


def ensure_status(conn, user_id, name, color, item_type, sort_order):
    row = conn.execute("select id from statuses where user_id=? and name=?", (user_id, name)).fetchone()
    if not row:
        conn.execute(
            "insert into statuses(user_id,name,color,type,sort_order,enabled) values(?,?,?,?,?,1)",
            (user_id, name, color, item_type, sort_order),
        )


def ensure_user_defaults(conn, user_id):
    for idx, item in enumerate(default_categories()):
        ensure_category(conn, user_id, item[0], item[1], item[2], idx)
    for idx, item in enumerate(default_statuses()):
        ensure_status(conn, user_id, item[0], item[1], item[2], idx)


def create_default_project_children(conn, project_id):
    for idx, name in enumerate(["01.项目启动", "02.项目过程", "03.项目完结"]):
        conn.execute("insert into document_dirs(project_id,parent_id,name,sort_order,deleted) values(?,null,?,?,0)", (project_id, name, idx))
    for idx, item in enumerate(["项目启动会", "现场踏勘与清单确认", "主材到场验收", "施工变更确认单", "联调测试"]):
        conn.execute(
            "insert into milestones(project_id,name,plan_date,status,sort_order,created_at,updated_at) values(?,?,?,?,?,?,?)",
            (project_id, item, (datetime.utcnow() + timedelta(days=idx)).date().isoformat(), "已完成" if idx < 3 else "进行中", idx, now(), now()),
        )
    conn.execute(
        "insert into project_logs(project_id,log_date,title,content,plain_text,updated_at) values(?,?,?,?,?,?)",
        (project_id, datetime.utcnow().date().isoformat(), "今日项目日志", "完成项目初始化记录。", "完成项目初始化记录。", now()),
    )
    conn.execute(
        "insert into people(project_id,name,organization,role,phone,email,wechat,note,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?)",
        (project_id, "李工", "客户信息中心", "技术确认人", "", "", "", "", now(), now()),
    )


SCHEMA = """
create table if not exists users (
  id integer primary key autoincrement,
  email text not null unique,
  nickname text not null,
  password_hash text not null,
  avatar text,
  role text not null default 'user',
  status text not null default 'active',
  last_login_at text,
  created_at text not null,
  updated_at text not null
);
create table if not exists email_codes (
  id integer primary key autoincrement,
  email text not null,
  code_hash text not null,
  purpose text not null,
  expires_at text not null,
  used integer not null default 0,
  ip text,
  created_at text not null
);
create table if not exists categories (
  id integer primary key autoincrement,
  user_id integer not null references users(id),
  name text not null,
  icon text not null default 'folder',
  color text not null default '#2563eb',
  sort_order integer not null default 0,
  enabled integer not null default 1
);
create table if not exists statuses (
  id integer primary key autoincrement,
  user_id integer not null references users(id),
  name text not null,
  color text not null default '#2563eb',
  type text not null default 'business',
  sort_order integer not null default 0,
  enabled integer not null default 1
);
create table if not exists projects (
  id integer primary key autoincrement,
  user_id integer not null references users(id),
  item_type text not null default 'project',
  name text not null,
  folder text not null,
  category_id integer references categories(id),
  start_date text,
  next_node_date text,
  next_node text,
  description text,
  contract_amount real not null default 0,
  invoiced_amount real not null default 0,
  received_amount real not null default 0,
  is_frozen integer not null default 0,
  is_deleted integer not null default 0,
  created_at text not null,
  updated_at text not null
);
create table if not exists project_statuses (
  project_id integer not null references projects(id) on delete cascade,
  status_id integer not null references statuses(id),
  primary key(project_id,status_id)
);
create table if not exists project_members (
  project_id integer not null references projects(id) on delete cascade,
  user_id integer not null references users(id),
  can_edit integer not null default 1,
  created_at text not null,
  primary key(project_id,user_id)
);
create table if not exists milestones (
  id integer primary key autoincrement,
  project_id integer not null references projects(id) on delete cascade,
  name text not null,
  plan_date text,
  completed_date text,
  status text not null default '未开始',
  owner text,
  note text,
  sort_order integer not null default 0,
  created_at text not null,
  updated_at text not null
);
create table if not exists project_logs (
  id integer primary key autoincrement,
  project_id integer not null references projects(id) on delete cascade,
  log_date text not null,
  title text,
  content text,
  plain_text text,
  updated_at text not null,
  unique(project_id, log_date)
);
create table if not exists document_dirs (
  id integer primary key autoincrement,
  project_id integer not null references projects(id) on delete cascade,
  parent_id integer references document_dirs(id),
  name text not null,
  sort_order integer not null default 0,
  deleted integer not null default 0
);
create table if not exists documents (
  id integer primary key autoincrement,
  project_id integer not null references projects(id) on delete cascade,
  dir_id integer references document_dirs(id),
  original_name text not null,
  stored_name text not null,
  file_type text,
  size_bytes integer not null default 0,
  storage_path text not null,
  description text,
  index_status text not null default '待处理',
  extracted_text text,
  deleted integer not null default 0,
  created_at text not null,
  updated_at text not null
);
create table if not exists people (
  id integer primary key autoincrement,
  project_id integer not null references projects(id) on delete cascade,
  name text not null,
  organization text,
  role text,
  phone text,
  email text,
  wechat text,
  note text,
  created_at text not null,
  updated_at text not null
);
create table if not exists folder_templates (
  id integer primary key autoincrement,
  user_id integer not null references users(id),
  name text not null,
  tree_json text not null,
  is_default integer not null default 0,
  created_at text not null
);
create table if not exists audit_logs (
  id integer primary key autoincrement,
  actor_id integer,
  object_type text,
  object_id integer,
  action text not null,
  details text,
  ip text,
  created_at text not null
);
"""
