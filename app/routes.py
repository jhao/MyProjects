import hashlib
import html
import json
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from .db import connect, execute, hash_password, now, query_all, query_one, verify_password


bp = Blueprint("main", __name__)


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return query_one("select * from users where id=?", (uid,))


def require_user():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "未登录"}), 401)
    if user["status"] != "active":
        return None, (jsonify({"error": "账号已被冻结"}), 403)
    return user, None


def require_admin():
    user, err = require_user()
    if err:
        return None, err
    if user["role"] != "admin":
        return None, (jsonify({"error": "需要管理员权限"}), 403)
    return user, None


def payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def clean_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def money_value(value):
    if value in (None, ""):
        return 0
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0


def current_item_type():
    return "personal" if request.args.get("item_type") == "personal" else "project"


def payload_item_type(data):
    return "personal" if data.get("item_type") == "personal" else "project"


def make_code(length=6):
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def validate_captcha(value):
    expected = session.get("captcha_code", "")
    return expected and clean_text(value).upper() == expected.upper()


def send_mail(to_email, subject, content):
    if current_app.config["MAIL_HOST"]:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = current_app.config["MAIL_FROM"]
        msg["To"] = to_email
        msg.set_content(content)
        with smtplib.SMTP(current_app.config["MAIL_HOST"], current_app.config["MAIL_PORT"]) as smtp:
            if current_app.config["MAIL_USE_TLS"]:
                smtp.starttls()
            if current_app.config["MAIL_USERNAME"]:
                smtp.login(current_app.config["MAIL_USERNAME"], current_app.config["MAIL_PASSWORD"])
            smtp.send_message(msg)
        return
    log_path = Path(current_app.config["DATA_DIR"]) / "dev_mailbox.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"[{now()}] to={to_email} subject={subject} content={content}\n")


def project_allowed(project_id, user):
    if user["role"] == "admin":
        return query_one("select * from projects where id=? and is_deleted=0", (project_id,))
    return query_one(
        """select p.* from projects p
           where p.id=? and p.is_deleted=0 and (
             p.user_id=?
             or (p.item_type='project' and exists(
               select 1 from project_members pm where pm.project_id=p.id and pm.user_id=? and pm.can_edit=1
             ))
           )""",
        (project_id, user["id"], user["id"]),
    )


def audit(actor_id, object_type, object_id, action, details=None):
    execute(
        "insert into audit_logs(actor_id,object_type,object_id,action,details,ip,created_at) values(?,?,?,?,?,?,?)",
        (actor_id, object_type, object_id, action, json.dumps(details, ensure_ascii=False) if isinstance(details, (dict, list)) else details, request.remote_addr or "", now()),
    )


def audit_project(user, project_id, action, details=None):
    audit(user["id"], "project", project_id, action, details)


def project_members(project_id):
    return query_all(
        """select u.id,u.email,u.nickname,pm.can_edit,pm.created_at
           from project_members pm join users u on u.id=pm.user_id
           where pm.project_id=? order by u.id""",
        (project_id,),
    )


def sync_project_members(conn, project_id, owner_id, member_ids):
    allowed = {owner_id}
    allowed.update(int(mid) for mid in member_ids if str(mid).isdigit())
    valid = {
        row["id"]
        for row in conn.execute(
            "select id from users where role<>'admin' and status='active' and id in ({})".format(",".join("?" for _ in allowed)),
            tuple(allowed),
        ).fetchall()
    } if allowed else set()
    valid.add(owner_id)
    conn.execute("delete from project_members where project_id=?", (project_id,))
    for uid in sorted(valid):
        conn.execute("insert or ignore into project_members(project_id,user_id,can_edit,created_at) values(?,?,1,?)", (project_id, uid, now()))


@bp.get("/")
def index():
    if not current_user():
        return redirect(url_for("main.auth_page"))
    return redirect(url_for("main.admin_page" if current_user()["role"] == "admin" else "main.app_page"))


@bp.get("/auth")
def auth_page():
    return render_template("auth.html")


@bp.get("/api/auth/captcha")
def captcha():
    code = make_code(4)
    session["captcha_code"] = code
    noise = "".join(f"<line x1='{secrets.randbelow(120)}' y1='{secrets.randbelow(42)}' x2='{secrets.randbelow(120)}' y2='{secrets.randbelow(42)}' stroke='#cbd5e1'/>" for _ in range(7))
    chars = "".join(f"<text x='{18 + idx * 22}' y='{28 + secrets.randbelow(6)}' rotate='{secrets.choice([-8,-4,0,5,8])}'>{ch}</text>" for idx, ch in enumerate(code))
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='120' height='42' viewBox='0 0 120 42'>
<rect width='120' height='42' rx='6' fill='#f8fafc'/>
{noise}
<g font-family='Arial, sans-serif' font-size='22' font-weight='700' fill='#1d4ed8'>{chars}</g>
</svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@bp.get("/app")
def app_page():
    if not current_user():
        return redirect(url_for("main.auth_page"))
    return render_template("app.html")


@bp.get("/admin")
def admin_page():
    user = current_user()
    if not user:
        return redirect(url_for("main.auth_page"))
    if user["role"] != "admin":
        return redirect(url_for("main.app_page"))
    return render_template("admin.html")


@bp.post("/api/auth/send-code")
def send_code():
    data = payload()
    email = clean_text(data.get("email")).lower()
    captcha = clean_text(data.get("captcha"))
    if not email or "@" not in email:
        return jsonify({"error": "邮箱格式不正确"}), 400
    if not validate_captcha(captcha):
        return jsonify({"error": "图形验证码错误"}), 400
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=5)).replace(microsecond=0).isoformat()
    purpose = data.get("purpose", "register")
    execute(
        "insert into email_codes(email,code_hash,purpose,expires_at,used,ip,created_at) values(?,?,?,?,0,?,?)",
        (email, code_hash, purpose, expires_at, request.remote_addr or "", now()),
    )
    send_mail(email, "事务项目管理系统验证码", f"您的验证码是：{code}，5分钟内有效。")
    return jsonify({"message": "验证码已发送"})


@bp.post("/api/auth/register")
def register():
    data = payload()
    email = clean_text(data.get("email")).lower()
    nickname = clean_text(data.get("nickname"))
    password = data.get("password") or ""
    code = clean_text(data.get("code"))
    if not email or not nickname or len(password) < 6:
        return jsonify({"error": "邮箱、昵称和至少 6 位密码必填"}), 400
    if query_one("select id from users where email=?", (email,)):
        return jsonify({"error": "邮箱已注册"}), 400
    item = query_one(
        "select * from email_codes where email=? and purpose='register' and used=0 order by id desc limit 1",
        (email,),
    )
    if not item or item["expires_at"] < datetime.utcnow().isoformat():
        return jsonify({"error": "验证码已过期"}), 400
    if hashlib.sha256(code.encode()).hexdigest() != item["code_hash"]:
        return jsonify({"error": "验证码错误"}), 400
    with connect() as conn:
        uid = conn.execute(
            "insert into users(email,nickname,password_hash,role,status,created_at,updated_at) values(?,?,?,?,?,?,?)",
            (email, nickname, hash_password(password), "user", "active", now(), now()),
        ).lastrowid
        conn.execute("update email_codes set used=1 where id=?", (item["id"],))
        from .db import seed_user_workspace

        seed_user_workspace(conn, uid)
    session["user_id"] = uid
    return jsonify({"message": "注册成功", "user": {"id": uid, "email": email, "nickname": nickname}})


@bp.post("/api/auth/login")
def login():
    data = payload()
    account = clean_text(data.get("account") or data.get("email")).lower()
    password = data.get("password") or ""
    if not validate_captcha(data.get("captcha")):
        return jsonify({"error": "图形验证码错误"}), 400
    user = query_one("select * from users where lower(email)=?", (account,))
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "账号或密码错误"}), 400
    if user["status"] != "active":
        return jsonify({"error": "账号已被冻结"}), 403
    session["user_id"] = user["id"]
    execute("update users set last_login_at=?,updated_at=? where id=?", (now(), now(), user["id"]))
    return jsonify({"message": "登录成功", "user": safe_user(user)})


@bp.post("/api/auth/reset-password")
def reset_password():
    data = payload()
    email = clean_text(data.get("email")).lower()
    code = clean_text(data.get("code"))
    password = data.get("password") or ""
    if not email or "@" not in email or len(password) < 6:
        return jsonify({"error": "邮箱和至少 6 位新密码必填"}), 400
    user = query_one("select * from users where email=? and role<>'admin'", (email,))
    if not user:
        return jsonify({"error": "邮箱不存在"}), 404
    item = query_one(
        "select * from email_codes where email=? and purpose='reset' and used=0 order by id desc limit 1",
        (email,),
    )
    if not item or item["expires_at"] < datetime.utcnow().isoformat():
        return jsonify({"error": "验证码已过期"}), 400
    if hashlib.sha256(code.encode()).hexdigest() != item["code_hash"]:
        return jsonify({"error": "验证码错误"}), 400
    with connect() as conn:
        conn.execute("update users set password_hash=?,updated_at=? where id=?", (hash_password(password), now(), user["id"]))
        conn.execute("update email_codes set used=1 where id=?", (item["id"],))
    return jsonify({"message": "密码已重置"})


@bp.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "已退出"})


@bp.post("/api/me/password")
def change_own_password():
    user, err = require_user()
    if err:
        return err
    data = payload()
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "新密码至少 6 位"}), 400
    if new_password != confirm_password:
        return jsonify({"error": "两次输入的新密码不一致"}), 400
    if not verify_password(old_password, user["password_hash"]):
        return jsonify({"error": "当前密码错误"}), 400
    execute("update users set password_hash=?,updated_at=? where id=?", (hash_password(new_password), now(), user["id"]))
    audit(user["id"], "user", user["id"], "change_own_password")
    return jsonify({"message": "密码已修改"})


@bp.get("/api/me")
def me():
    user = current_user()
    return jsonify({"user": safe_user(user) if user else None})


def safe_user(user):
    if not user:
        return None
    return {k: user[k] for k in ["id", "email", "nickname", "avatar", "role", "status", "last_login_at"] if k in user.keys()}


@bp.get("/api/users/options")
def user_options():
    user, err = require_user()
    if err:
        return err
    rows = query_all("select id,email,nickname from users where role<>'admin' and status='active' order by nickname,email")
    return jsonify({"items": rows})


@bp.get("/api/categories")
def categories():
    user, err = require_user()
    if err:
        return err
    rows = query_all("select * from categories where user_id=? and enabled=1 order by sort_order,id", (user["id"],))
    return jsonify({"items": rows})


@bp.post("/api/categories")
def create_category():
    user, err = require_user()
    if err:
        return err
    data = payload()
    cid = execute(
        "insert into categories(user_id,name,icon,color,sort_order,enabled) values(?,?,?,?,?,1)",
        (user["id"], clean_text(data.get("name")), data.get("icon") or "folder", data.get("color") or "#2563eb", int(data.get("sort_order") or 0)),
    )
    audit(user["id"], "category", cid, "create")
    return jsonify({"id": cid})


@bp.get("/api/statuses")
def statuses():
    user, err = require_user()
    if err:
        return err
    rows = query_all("select * from statuses where user_id=? and enabled=1 order by sort_order,id", (user["id"],))
    return jsonify({"items": rows})


@bp.post("/api/statuses")
def create_status():
    user, err = require_user()
    if err:
        return err
    data = payload()
    sid = execute(
        "insert into statuses(user_id,name,color,type,sort_order,enabled) values(?,?,?,?,?,1)",
        (user["id"], clean_text(data.get("name")), data.get("color") or "#2563eb", data.get("type") or "business", int(data.get("sort_order") or 0)),
    )
    audit(user["id"], "status", sid, "create")
    return jsonify({"id": sid})


@bp.get("/api/projects")
def list_projects():
    user, err = require_user()
    if err:
        return err
    args = request.args
    page = max(int(args.get("page", 1)), 1)
    per_page = min(max(int(args.get("per_page", 10)), 1), 100)
    sort = args.get("sort", "updated_at")
    direction = "asc" if args.get("direction") == "asc" else "desc"
    base, params, sortable = build_project_query(user, args)
    total = query_one("select count(*) as total from (" + base + ")", params)["total"]
    category_amounts = query_all(
        """select category_id,
                  coalesce(category_name, '未分类') as category_name,
                  coalesce(category_color, '#64748b') as category_color,
                  coalesce(sum(contract_amount),0) as contract_amount,
                  coalesce(sum(invoiced_amount),0) as invoiced_amount,
                  coalesce(sum(received_amount),0) as received_amount
           from (""" + base + """) filtered_projects
           group by category_id, category_name, category_color
           order by category_name""",
        params,
    )
    order_by = sortable.get(sort, "p.updated_at")
    rows = query_all(base + f" order by {order_by} {direction} limit ? offset ?", params + [per_page, (page - 1) * per_page])
    for row in rows:
        row["statuses"] = project_status_list(row["id"])
    return jsonify({"items": rows, "total": total, "page": page, "per_page": per_page, "category_amounts": category_amounts})


def build_project_query(user, args):
    sortable = {
        "name": "p.name",
        "folder": "p.folder",
        "category": "c.name",
        "start_date": "p.start_date",
        "updated_at": "p.updated_at",
        "next_node_date": "p.next_node_date",
        "milestone": "milestone_done * 1.0 / nullif(milestone_total,0)",
        "amounts": "p.received_amount",
    }
    item_type = "personal" if args.get("item_type") == "personal" else "project"
    params = [item_type]
    where = ["p.item_type=?", "p.is_deleted=0"]
    if user["role"] != "admin":
        if item_type == "personal":
            where.append("p.user_id=?")
            params.append(user["id"])
        else:
            where.append("(p.user_id=? or exists(select 1 from project_members pm where pm.project_id=p.id and pm.user_id=? and pm.can_edit=1))")
            params.extend([user["id"], user["id"]])
    if args.get("folder"):
        where.append("p.folder like ?")
        params.append(f"%{args['folder']}%")
    if args.get("q"):
        where.append("(p.name like ? or p.description like ? or exists(select 1 from project_logs l where l.project_id=p.id and l.plain_text like ?) or exists(select 1 from documents d where d.project_id=p.id and d.deleted=0 and (d.original_name like ? or d.extracted_text like ?)))")
        like = f"%{args['q']}%"
        params.extend([like, like, like, like, like])
    for key, col in [("start_from", "p.start_date"), ("updated_from", "p.updated_at")]:
        if args.get(key):
            where.append(f"{col}>=?")
            params.append(args[key])
    for key, col in [("start_to", "p.start_date"), ("updated_to", "p.updated_at")]:
        if args.get(key):
            where.append(f"{col}<=?")
            params.append(args[key])
    category_ids = [x for x in args.getlist("category_ids") if x]
    if category_ids:
        where.append(f"p.category_id in ({','.join('?' for _ in category_ids)})")
        params.extend(category_ids)
    status_ids = [x for x in args.getlist("status_ids") if x]
    if status_ids:
        where.append(f"exists(select 1 from project_statuses ps where ps.project_id=p.id and ps.status_id in ({','.join('?' for _ in status_ids)}))")
        params.extend(status_ids)
    base = PROJECT_SELECT + " where " + " and ".join(where)
    return base, params, sortable


@bp.get("/api/projects/export")
def export_projects():
    user, err = require_user()
    if err:
        return err
    args = request.args
    sort = args.get("sort", "updated_at")
    direction = "asc" if args.get("direction") == "asc" else "desc"
    base, params, sortable = build_project_query(user, args)
    rows = query_all(base + f" order by {sortable.get(sort, 'p.updated_at')} {direction}", params)
    for row in rows:
        row["statuses"] = project_status_list(row["id"])
    headers = ["项目名称", "所属目录", "分类", "启动日期", "状态", "合同额", "已开票金额", "已回款金额", "最后更新", "最新日志", "下一步节点日期", "下一步节点", "里程碑"]
    table_rows = ["<tr>" + "".join(f"<th>{html.escape(col)}</th>" for col in headers) + "</tr>"]
    for row in rows:
        values = [
            row["name"],
            row["folder"],
            row.get("category_name") or "",
            row.get("start_date") or "",
            "、".join(s["name"] for s in row["statuses"]),
            row.get("contract_amount") or 0,
            row.get("invoiced_amount") or 0,
            row.get("received_amount") or 0,
            (row.get("updated_at") or "")[:10],
            row.get("latest_log_text") or "",
            row.get("next_node_date") or "",
            row.get("next_node") or "",
            f"{row.get('milestone_done') or 0}/{row.get('milestone_total') or 0}",
        ]
        table_rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in values) + "</tr>")
    content = "\ufeff<html><head><meta charset='utf-8'></head><body><table border='1'>" + "".join(table_rows) + "</table></body></html>"
    return Response(
        content,
        mimetype="application/vnd.ms-excel; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=projects.xls"},
    )


PROJECT_SELECT = """
select p.*, c.name as category_name, c.color as category_color, c.icon as category_icon,
       (select count(*) from milestones m where m.project_id=p.id) as milestone_total,
       (select count(*) from milestones m where m.project_id=p.id and m.status='已完成') as milestone_done,
       (select max(log_date) from project_logs l where l.project_id=p.id) as latest_log_date,
       (select l.plain_text from project_logs l where l.project_id=p.id order by l.log_date desc, l.updated_at desc limit 1) as latest_log_text
from projects p
left join categories c on c.id=p.category_id
"""


def project_status_list(project_id):
    return query_all(
        "select s.* from statuses s join project_statuses ps on ps.status_id=s.id where ps.project_id=? order by s.sort_order,s.id",
        (project_id,),
    )


@bp.post("/api/projects")
def create_project():
    user, err = require_user()
    if err:
        return err
    data = payload()
    name = clean_text(data.get("name"))
    folder = clean_text(data.get("folder"))
    item_type = payload_item_type(data)
    if not name or not folder:
        return jsonify({"error": "项目名称和所属目录必填"}), 400
    with connect() as conn:
        pid = conn.execute(
            """insert into projects(user_id,item_type,name,folder,category_id,start_date,next_node_date,next_node,description,
               contract_amount,invoiced_amount,received_amount,is_frozen,is_deleted,created_at,updated_at)
               values(?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)""",
            (
                user["id"],
                item_type,
                name,
                folder,
                data.get("category_id"),
                data.get("start_date"),
                data.get("next_node_date"),
                data.get("next_node"),
                data.get("description"),
                money_value(data.get("contract_amount")),
                money_value(data.get("invoiced_amount")),
                money_value(data.get("received_amount")),
                now(),
                now(),
            ),
        ).lastrowid
        for sid in data.get("status_ids", []) if isinstance(data.get("status_ids"), list) else request.form.getlist("status_ids"):
            conn.execute("insert or ignore into project_statuses(project_id,status_id) values(?,?)", (pid, sid))
        if item_type == "project":
            member_ids = data.get("member_ids", []) if isinstance(data.get("member_ids"), list) else request.form.getlist("member_ids")
            sync_project_members(conn, pid, user["id"], member_ids)
        default_dirs = ["01.事务启动", "02.事务过程", "03.事务完结"] if item_type == "personal" else ["01.项目启动", "02.项目过程", "03.项目完结"]
        for idx, dirname in enumerate(default_dirs):
            conn.execute("insert into document_dirs(project_id,parent_id,name,sort_order,deleted) values(?,null,?,?,0)", (pid, dirname, idx))
    audit_project(user, pid, "create", {"name": name, "item_type": item_type})
    return jsonify({"id": pid})


@bp.get("/api/projects/<int:project_id>")
def get_project(project_id):
    user, err = require_user()
    if err:
        return err
    project = project_allowed(project_id, user)
    if not project:
        return jsonify({"error": "项目不存在"}), 404
    project["statuses"] = project_status_list(project_id)
    project["members"] = project_members(project_id) if project.get("item_type") == "project" else []
    return jsonify({"project": project})


@bp.put("/api/projects/<int:project_id>")
def update_project(project_id):
    user, err = require_user()
    if err:
        return err
    project = project_allowed(project_id, user)
    if not project:
        return jsonify({"error": "项目不存在"}), 404
    data = payload()
    with connect() as conn:
        conn.execute(
            """update projects set name=?,folder=?,category_id=?,start_date=?,next_node_date=?,next_node=?,description=?,
               contract_amount=?,invoiced_amount=?,received_amount=?,updated_at=? where id=?""",
            (
                data.get("name"),
                data.get("folder"),
                data.get("category_id"),
                data.get("start_date"),
                data.get("next_node_date"),
                data.get("next_node"),
                data.get("description"),
                money_value(data.get("contract_amount")),
                money_value(data.get("invoiced_amount")),
                money_value(data.get("received_amount")),
                now(),
                project_id,
            ),
        )
        conn.execute("delete from project_statuses where project_id=?", (project_id,))
        status_ids = data.get("status_ids", []) if isinstance(data.get("status_ids"), list) else request.form.getlist("status_ids")
        for sid in status_ids:
            conn.execute("insert or ignore into project_statuses(project_id,status_id) values(?,?)", (project_id, sid))
        if project.get("item_type") == "project":
            member_ids = data.get("member_ids", []) if isinstance(data.get("member_ids"), list) else request.form.getlist("member_ids")
            sync_project_members(conn, project_id, project["user_id"], member_ids)
    audit_project(user, project_id, "update", {"name": data.get("name"), "item_type": project.get("item_type")})
    return jsonify({"message": "已保存"})


@bp.post("/api/projects/<int:project_id>/state")
def update_project_state(project_id):
    user, err = require_user()
    if err:
        return err
    project = project_allowed(project_id, user)
    if not project:
        return jsonify({"error": "项目不存在"}), 404
    action = payload().get("action")
    if action == "freeze":
        execute("update projects set is_frozen=1,updated_at=? where id=?", (now(), project_id))
    elif action == "start":
        execute("update projects set is_frozen=0,updated_at=? where id=?", (now(), project_id))
    elif action == "delete":
        execute("update projects set is_deleted=1,updated_at=? where id=?", (now(), project_id))
    else:
        return jsonify({"error": "未知操作"}), 400
    audit_project(user, project_id, action)
    return jsonify({"message": "操作成功"})


@bp.get("/api/projects/<int:project_id>/audit-logs")
def project_audit_logs(project_id):
    user, err = require_user()
    if err:
        return err
    project = project_allowed(project_id, user)
    if not project:
        return jsonify({"error": "项目不存在"}), 404
    rows = query_all(
        """select a.*,u.nickname,u.email
           from audit_logs a left join users u on u.id=a.actor_id
           where a.object_type='project' and a.object_id=?
           order by a.created_at desc,a.id desc limit 200""",
        (project_id,),
    )
    return jsonify({"items": rows})


@bp.route("/api/projects/<int:project_id>/milestones", methods=["GET", "POST"])
def milestones(project_id):
    user, err = require_user()
    if err:
        return err
    project = project_allowed(project_id, user)
    if not project:
        return jsonify({"error": "项目不存在"}), 404
    if request.method == "GET":
        return jsonify({"items": query_all("select * from milestones where project_id=? order by sort_order,id", (project_id,))})
    data = payload()
    mid = execute(
        "insert into milestones(project_id,name,plan_date,completed_date,status,owner,note,sort_order,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?)",
        (project_id, data.get("name"), data.get("plan_date"), data.get("completed_date"), data.get("status") or "未开始", data.get("owner"), data.get("note"), int(data.get("sort_order") or 0), now(), now()),
    )
    audit_project(user, project_id, "milestone_create", {"milestone_id": mid, "name": data.get("name")})
    return jsonify({"id": mid})


@bp.put("/api/milestones/<int:item_id>")
def update_milestone(item_id):
    user, err = require_user()
    if err:
        return err
    item = query_one("select * from milestones where id=?", (item_id,))
    if not item or not project_allowed(item["project_id"], user):
        return jsonify({"error": "里程碑不存在"}), 404
    data = payload()
    execute(
        "update milestones set name=?,plan_date=?,completed_date=?,status=?,owner=?,note=?,sort_order=?,updated_at=? where id=?",
        (data.get("name"), data.get("plan_date"), data.get("completed_date"), data.get("status"), data.get("owner"), data.get("note"), int(data.get("sort_order") or 0), now(), item_id),
    )
    audit_project(user, item["project_id"], "milestone_update", {"milestone_id": item_id, "name": data.get("name")})
    return jsonify({"message": "已保存"})


@bp.post("/api/projects/<int:project_id>/milestones/reorder")
def reorder_milestones(project_id):
    user, err = require_user()
    if err:
        return err
    if not project_allowed(project_id, user):
        return jsonify({"error": "项目不存在"}), 404
    item_ids = payload().get("item_ids") or []
    if not isinstance(item_ids, list):
        return jsonify({"error": "排序数据格式不正确"}), 400
    owned = {
        row["id"]
        for row in query_all("select id from milestones where project_id=?", (project_id,))
    }
    ordered_ids = [int(item_id) for item_id in item_ids if int(item_id) in owned]
    with connect() as conn:
        for index, item_id in enumerate(ordered_ids):
            conn.execute("update milestones set sort_order=?,updated_at=? where id=?", (index, now(), item_id))
        conn.execute("update projects set updated_at=? where id=?", (now(), project_id))
    audit_project(user, project_id, "milestone_reorder", {"item_ids": ordered_ids})
    return jsonify({"message": "排序已保存"})


@bp.delete("/api/milestones/<int:item_id>")
def delete_milestone(item_id):
    user, err = require_user()
    if err:
        return err
    item = query_one("select * from milestones where id=?", (item_id,))
    if not item or not project_allowed(item["project_id"], user):
        return jsonify({"error": "里程碑不存在"}), 404
    execute("delete from milestones where id=?", (item_id,))
    audit_project(user, item["project_id"], "milestone_delete", {"milestone_id": item_id, "name": item.get("name")})
    return jsonify({"message": "已删除"})


@bp.route("/api/projects/<int:project_id>/logs", methods=["GET", "POST"])
def project_logs(project_id):
    user, err = require_user()
    if err:
        return err
    project = project_allowed(project_id, user)
    if not project:
        return jsonify({"error": "项目不存在"}), 404
    if request.method == "GET":
        date = request.args.get("date")
        keyword = clean_text(request.args.get("q"))
        if date:
            return jsonify({"item": query_one("select * from project_logs where project_id=? and log_date=?", (project_id, date))})
        if keyword:
            like = f"%{keyword}%"
            return jsonify({
                "items": query_all(
                    """select id,project_id,log_date,title,plain_text,updated_at
                       from project_logs
                       where project_id=? and (title like ? or plain_text like ?)
                       order by log_date desc limit 50""",
                    (project_id, like, like),
                )
            })
        return jsonify({"items": query_all("select * from project_logs where project_id=? order by log_date desc", (project_id,))})
    data = payload()
    log_date = data.get("log_date") or datetime.utcnow().date().isoformat()
    content = data.get("content") or ""
    plain = re.sub("<[^>]+>", " ", content)
    with connect() as conn:
        conn.execute(
            """insert into project_logs(project_id,log_date,title,content,plain_text,updated_at) values(?,?,?,?,?,?)
               on conflict(project_id,log_date) do update set title=excluded.title,content=excluded.content,plain_text=excluded.plain_text,updated_at=excluded.updated_at""",
            (project_id, log_date, data.get("title") or f"{log_date} {'事务' if project.get('item_type') == 'personal' else '项目'}日志", content, plain, now()),
        )
        conn.execute("update projects set updated_at=? where id=?", (now(), project_id))
    audit_project(user, project_id, "log_save", {"log_date": log_date, "title": data.get("title")})
    return jsonify({"message": "日志已保存"})


@bp.route("/api/projects/<int:project_id>/dirs", methods=["GET", "POST"])
def dirs(project_id):
    user, err = require_user()
    if err:
        return err
    if not project_allowed(project_id, user):
        return jsonify({"error": "项目不存在"}), 404
    if request.method == "GET":
        return jsonify({"items": query_all("select * from document_dirs where project_id=? and deleted=0 order by parent_id,sort_order,id", (project_id,))})
    data = payload()
    did = execute(
        "insert into document_dirs(project_id,parent_id,name,sort_order,deleted) values(?,?,?,?,0)",
        (project_id, data.get("parent_id"), data.get("name"), int(data.get("sort_order") or 0)),
    )
    audit_project(user, project_id, "dir_create", {"dir_id": did, "name": data.get("name")})
    return jsonify({"id": did})


@bp.route("/api/projects/<int:project_id>/documents", methods=["GET", "POST"])
def documents(project_id):
    user, err = require_user()
    if err:
        return err
    if not project_allowed(project_id, user):
        return jsonify({"error": "项目不存在"}), 404
    if request.method == "GET":
        dir_id = request.args.get("dir_id")
        if dir_id == "root":
            rows = query_all("select * from documents where project_id=? and dir_id is null and deleted=0 order by created_at desc", (project_id,))
        elif dir_id:
            rows = query_all("select * from documents where project_id=? and dir_id=? and deleted=0 order by created_at desc", (project_id, dir_id))
        else:
            rows = query_all("select * from documents where project_id=? and deleted=0 order by created_at desc", (project_id,))
        return jsonify({"items": rows})
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "请选择文件"}), 400
    upload_root = Path(current_app.config["UPLOAD_DIR"]) / str(user["id"]) / str(project_id)
    upload_root.mkdir(parents=True, exist_ok=True)
    saved = []
    for file in files:
        original = file.filename or "upload.bin"
        safe = secure_filename(original) or "upload.bin"
        stored = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe}"
        path = upload_root / stored
        file.save(path)
        suffix = path.suffix.lower().lstrip(".")
        extracted = ""
        if suffix in {"txt", "md", "markdown", "csv"}:
            extracted = path.read_text(errors="ignore")[:200000]
        doc_id = execute(
            """insert into documents(project_id,dir_id,original_name,stored_name,file_type,size_bytes,storage_path,description,index_status,extracted_text,deleted,created_at,updated_at)
               values(?,?,?,?,?,?,?,?,?,?,0,?,?)""",
            (project_id, normalize_dir_id(request.form.get("dir_id")), original, stored, suffix, path.stat().st_size, str(path), request.form.get("description"), "已索引" if extracted else "待处理", extracted, now(), now()),
        )
        saved.append({"id": doc_id, "name": original})
    audit_project(user, project_id, "document_upload", {"files": saved})
    return jsonify({"items": saved})


@bp.put("/api/dirs/<int:dir_id>")
def update_dir(dir_id):
    user, err = require_user()
    if err:
        return err
    item = query_one("select * from document_dirs where id=? and deleted=0", (dir_id,))
    if not item or not project_allowed(item["project_id"], user):
        return jsonify({"error": "目录不存在"}), 404
    data = payload()
    parent_id = data.get("parent_id")
    if parent_id in ("", "null", "root"):
        parent_id = None
    if parent_id:
        parent = query_one("select * from document_dirs where id=? and project_id=? and deleted=0", (parent_id, item["project_id"]))
        if not parent:
            return jsonify({"error": "目标目录不存在"}), 400
        if int(parent_id) == dir_id or int(parent_id) in descendant_dir_ids(dir_id):
            return jsonify({"error": "不能移动到自身或子目录下"}), 400
    execute(
        "update document_dirs set name=?,parent_id=?,sort_order=? where id=?",
        (data.get("name") or item["name"], parent_id, int(data.get("sort_order") or item["sort_order"] or 0), dir_id),
    )
    audit_project(user, item["project_id"], "dir_update", {"dir_id": dir_id, "name": data.get("name") or item["name"]})
    return jsonify({"message": "目录已保存"})


@bp.delete("/api/dirs/<int:dir_id>")
def delete_dir(dir_id):
    user, err = require_user()
    if err:
        return err
    item = query_one("select * from document_dirs where id=? and deleted=0", (dir_id,))
    if not item or not project_allowed(item["project_id"], user):
        return jsonify({"error": "目录不存在"}), 404
    ids = [dir_id] + descendant_dir_ids(dir_id)
    with connect() as conn:
        for item_id in ids:
            conn.execute("update document_dirs set deleted=1 where id=?", (item_id,))
            conn.execute("update documents set deleted=1,updated_at=? where dir_id=?", (now(), item_id))
        conn.execute("update projects set updated_at=? where id=?", (now(), item["project_id"]))
    audit_project(user, item["project_id"], "dir_delete", {"dir_id": dir_id, "name": item.get("name")})
    return jsonify({"message": "目录已删除"})


def descendant_dir_ids(dir_id):
    children = query_all("select id from document_dirs where parent_id=? and deleted=0", (dir_id,))
    result = []
    for child in children:
        result.append(child["id"])
        result.extend(descendant_dir_ids(child["id"]))
    return result


@bp.get("/api/documents/<int:doc_id>/download")
def download_document(doc_id):
    user, err = require_user()
    if err:
        return err
    doc = query_one("select * from documents where id=? and deleted=0", (doc_id,))
    if not doc or not project_allowed(doc["project_id"], user):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(doc["storage_path"], as_attachment=False, download_name=doc["original_name"])


@bp.route("/api/documents/<int:doc_id>", methods=["PUT"])
@bp.route("/api/documents/<int:doc_id>/move", methods=["POST"])
@bp.route("/api/projects/<int:project_id>/documents/<int:doc_id>/move", methods=["POST"])
def update_document(doc_id, project_id=None):
    user, err = require_user()
    if err:
        return err
    doc = query_one("select * from documents where id=? and deleted=0", (doc_id,))
    if not doc or not project_allowed(doc["project_id"], user):
        return jsonify({"error": "文件不存在"}), 404
    if project_id is not None and doc["project_id"] != project_id:
        return jsonify({"error": "文件不属于当前项目"}), 404
    data = payload()
    dir_id = normalize_dir_id(data.get("dir_id"))
    if dir_id:
        target = query_one("select * from document_dirs where id=? and project_id=? and deleted=0", (dir_id, doc["project_id"]))
        if not target:
            return jsonify({"error": "目标目录不存在"}), 400
    execute("update documents set dir_id=?,updated_at=? where id=?", (dir_id, now(), doc_id))
    audit_project(user, doc["project_id"], "document_move", {"document_id": doc_id, "name": doc.get("original_name"), "dir_id": dir_id})
    return jsonify({"message": "文件已移动"})


def normalize_dir_id(value):
    if value in (None, "", "null", "root"):
        return None
    return value


@bp.route("/api/documents/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    user, err = require_user()
    if err:
        return err
    doc = query_one("select * from documents where id=?", (doc_id,))
    if not doc or not project_allowed(doc["project_id"], user):
        return jsonify({"error": "文件不存在"}), 404
    execute("update documents set deleted=1,updated_at=? where id=?", (now(), doc_id))
    audit_project(user, doc["project_id"], "document_delete", {"document_id": doc_id, "name": doc.get("original_name")})
    return jsonify({"message": "已删除"})


@bp.route("/api/projects/<int:project_id>/people", methods=["GET", "POST"])
def people(project_id):
    user, err = require_user()
    if err:
        return err
    if not project_allowed(project_id, user):
        return jsonify({"error": "项目不存在"}), 404
    if request.method == "GET":
        return jsonify({"items": query_all("select * from people where project_id=? order by id", (project_id,))})
    data = payload()
    pid = execute(
        "insert into people(project_id,name,organization,role,phone,email,wechat,note,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?)",
        (project_id, data.get("name"), data.get("organization"), data.get("role"), data.get("phone"), data.get("email"), data.get("wechat"), data.get("note"), now(), now()),
    )
    audit_project(user, project_id, "person_create", {"person_id": pid, "name": data.get("name")})
    return jsonify({"id": pid})


@bp.put("/api/people/<int:item_id>")
def update_person(item_id):
    user, err = require_user()
    if err:
        return err
    item = query_one("select * from people where id=?", (item_id,))
    if not item or not project_allowed(item["project_id"], user):
        return jsonify({"error": "相关人不存在"}), 404
    data = payload()
    execute(
        "update people set name=?,organization=?,role=?,phone=?,email=?,wechat=?,note=?,updated_at=? where id=?",
        (data.get("name"), data.get("organization"), data.get("role"), data.get("phone"), data.get("email"), data.get("wechat"), data.get("note"), now(), item_id),
    )
    audit_project(user, item["project_id"], "person_update", {"person_id": item_id, "name": data.get("name")})
    return jsonify({"message": "已保存"})


@bp.delete("/api/people/<int:item_id>")
def delete_person(item_id):
    user, err = require_user()
    if err:
        return err
    item = query_one("select * from people where id=?", (item_id,))
    if not item or not project_allowed(item["project_id"], user):
        return jsonify({"error": "相关人不存在"}), 404
    execute("delete from people where id=?", (item_id,))
    audit_project(user, item["project_id"], "person_delete", {"person_id": item_id, "name": item.get("name")})
    return jsonify({"message": "已删除"})


@bp.get("/api/admin/users")
def admin_users():
    admin, err = require_admin()
    if err:
        return err
    rows = query_all(
        """select u.id,u.email,u.nickname,u.role,u.status,u.last_login_at,u.created_at,u.updated_at,
                  (select count(*) from projects p where p.user_id=u.id and p.is_deleted=0) as project_count,
                  (select count(*) from documents d join projects p on p.id=d.project_id where p.user_id=u.id and d.deleted=0) as file_count,
                  coalesce((select sum(d.size_bytes) from documents d join projects p on p.id=d.project_id where p.user_id=u.id and d.deleted=0),0) as disk_usage
           from users u where u.role<>'admin' order by u.id"""
    )
    return jsonify({"items": rows})


@bp.post("/api/admin/users")
def admin_create_user():
    admin, err = require_admin()
    if err:
        return err
    data = payload()
    uid = execute(
        "insert into users(email,nickname,password_hash,role,status,created_at,updated_at) values(?,?,?,?,?,?,?)",
        (clean_text(data.get("email")).lower(), clean_text(data.get("nickname")), hash_password(data.get("password") or "Init123456"), "user", data.get("status") or "active", now(), now()),
    )
    audit(admin["id"], "user", uid, "create")
    return jsonify({"id": uid})


@bp.put("/api/admin/users/<int:user_id>")
def admin_update_user(user_id):
    admin, err = require_admin()
    if err:
        return err
    data = payload()
    execute(
        "update users set email=?,nickname=?,role=?,status=?,updated_at=? where id=?",
        (clean_text(data.get("email")).lower(), clean_text(data.get("nickname")), "user", data.get("status") or "active", now(), user_id),
    )
    audit(admin["id"], "user", user_id, "update")
    return jsonify({"message": "已保存"})


@bp.post("/api/admin/users/<int:user_id>/reset-password")
def admin_reset_password(user_id):
    admin, err = require_admin()
    if err:
        return err
    password = payload().get("password") or "Reset123456"
    execute("update users set password_hash=?,updated_at=? where id=?", (hash_password(password), now(), user_id))
    audit(admin["id"], "user", user_id, "reset_password")
    return jsonify({"message": "密码已重置", "temporary_password": password})


@bp.get("/api/admin/statuses")
def admin_statuses():
    admin, err = require_admin()
    if err:
        return err
    owner = query_one("select id from users where role<>'admin' order by id limit 1")
    if not owner:
        return jsonify({"items": []})
    rows = query_all("select * from statuses where user_id=? order by sort_order,id", (owner["id"],))
    return jsonify({"items": rows})


@bp.post("/api/admin/statuses")
def admin_create_status():
    admin, err = require_admin()
    if err:
        return err
    data = payload()
    name = clean_text(data.get("name"))
    if not name:
        return jsonify({"error": "状态名称必填"}), 400
    color = data.get("color") or "#2563eb"
    item_type = data.get("type") or "business"
    sort_order = int(data.get("sort_order") or 0)
    with connect() as conn:
        for user in conn.execute("select id from users where role<>'admin'"):
            exists = conn.execute("select id from statuses where user_id=? and name=?", (user["id"], name)).fetchone()
            if exists:
                conn.execute("update statuses set color=?,type=?,sort_order=?,enabled=1 where id=?", (color, item_type, sort_order, exists["id"]))
            else:
                conn.execute(
                    "insert into statuses(user_id,name,color,type,sort_order,enabled) values(?,?,?,?,?,1)",
                    (user["id"], name, color, item_type, sort_order),
                )
    audit(admin["id"], "status", None, f"create:{name}")
    return jsonify({"message": "状态已保存"})


@bp.put("/api/admin/statuses/<int:status_id>")
def admin_update_status(status_id):
    admin, err = require_admin()
    if err:
        return err
    item = query_one("select * from statuses where id=?", (status_id,))
    if not item:
        return jsonify({"error": "状态不存在"}), 404
    data = payload()
    old_name = item["name"]
    name = clean_text(data.get("name")) or old_name
    color = data.get("color") or item["color"]
    item_type = data.get("type") or item["type"]
    sort_order = int(data.get("sort_order") or item["sort_order"] or 0)
    enabled = 1 if str(data.get("enabled", "1")) in ("1", "true", "active") else 0
    execute(
        "update statuses set name=?,color=?,type=?,sort_order=?,enabled=? where name=?",
        (name, color, item_type, sort_order, enabled, old_name),
    )
    audit(admin["id"], "status", status_id, f"update:{old_name}->{name}")
    return jsonify({"message": "状态已保存"})
