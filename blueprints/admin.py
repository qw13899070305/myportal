import html as _html
from flask import Blueprint, render_template, request, redirect, session, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, shutil, uuid, time, secrets, logging
from config import Config
from utils import (admin_req, super_req, get_db, safe_path, is_allowed_file,
                   unique_path, move_trash, all_dirs, list_dir, crumbs, send_email,
                   audit_log, captcha, verify_captcha, check_ip_throttle,
                   record_ip_fail, reset_ip_throttle, render_article_content)
from models import init_db

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ==================== 面板首页 ====================
@admin_bp.route('/')
@admin_req
def panel():
    db = get_db()
    row = db.execute("SELECT role FROM admins WHERE username = ?", (session["admin_username"],)).fetchone()
    is_super = row["role"] == "super"
    pend = [r["username"] for r in db.execute("SELECT username FROM pending_admins").fetchall()]
    article_count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    pending_article_count = db.execute("SELECT COUNT(*) FROM pending_articles WHERE is_draft = 0").fetchone()[0]
    user_count = db.execute("SELECT COUNT(*) FROM chat_users").fetchone()[0]
    author_count = db.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    return render_template("admin_panel.html", article_count=article_count,
                           pending_article_count=pending_article_count,
                           author_count=author_count, user_count=user_count,
                           is_super=is_super, pend=pend)

# ==================== 登录/登出 ====================
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get("admin_username"):
        return redirect("/admin")
    error = None
    lock_remain = 0
    ip = request.remote_addr
    next_url = request.form.get("next") or request.args.get("next") or "/admin"
    is_internal = "/internal" in (next_url or "")
    if request.method == "POST":
        allowed, remain = check_ip_throttle(ip)
        if not allowed:
            lock_remain = remain
            error = f"登录尝试过多，请等待 {remain} 秒后再试"
        else:
            u = request.form.get("username", "").strip()
            p = request.form.get("password", "")
            db = get_db()
            row = db.execute("SELECT password, role FROM admins WHERE username = ?", (u,)).fetchone()
            if not row or not verify_pw(row["password"], p, "admins", u):
                error = "用户名或密码错误"
                record_ip_fail(ip)
                if is_internal:
                    return render_template("internal_login.html", next=next_url, admin_error=error, author_error=None)
            else:
                reset_ip_throttle(ip)
                session.permanent = True
                session["admin_username"] = u
                audit_log.info(f"管理员登录: {u} 从 {ip}")
                return redirect(next_url)
    return render_template("login.html", error=error, lock_remain=lock_remain)

@admin_bp.route('/logout')
def logout():
    session.pop("admin_username", None)
    return redirect("/")

# ==================== 管理员审核 ====================
@admin_bp.route('/approve_admin', methods=['POST'])
@super_req
def approve_admin():
    u = request.form.get("username", "").strip()
    db = get_db()
    row = db.execute("SELECT password FROM pending_admins WHERE username = ?", (u,)).fetchone()
    if row:
        db.execute("INSERT INTO admins (username, password, role) VALUES (?, ?, ?)", (u, row["password"], "admin"))
        db.execute("DELETE FROM pending_admins WHERE username = ?", (u,))
        db.commit()
        audit_log.info(f"批准管理员: {u}")
    return redirect("/admin")

@admin_bp.route('/reject_admin', methods=['POST'])
@super_req
def reject_admin():
    u = request.form.get("username", "").strip()
    db = get_db()
    db.execute("DELETE FROM pending_admins WHERE username = ?", (u,))
    db.commit()
    return redirect("/admin")

# ==================== 管理员管理 ====================
@admin_bp.route('/manage_admins')
@admin_req
def manage_admins():
    db = get_db()
    is_super = db.execute("SELECT role FROM admins WHERE username = ?", (session["admin_username"],)).fetchone()["role"] == "super"
    admins = [{"username": r["username"], "role": r["role"]} for r in db.execute("SELECT username, role FROM admins")]
    return render_template("admin_manage.html", admins=admins, current_user=session["admin_username"], is_super=is_super)

@admin_bp.route('/remove_admin', methods=['POST'])
@super_req
def remove_admin():
    u = request.form.get("username", "").strip()
    if u == session["admin_username"]:
        return "不能移除自己", 403
    db = get_db()
    db.execute("DELETE FROM admins WHERE username = ?", (u,))
    db.commit()
    return redirect("/admin/manage_admins")

# ==================== 文件管理 ====================
@admin_bp.route('/manage_files', defaults={'subpath': ''})
@admin_bp.route('/manage_files/<path:subpath>')
@admin_req
def manage_files(subpath):
    path = safe_path(Config.SHARE_DIR, subpath) if subpath else Config.SHARE_DIR
    if not os.path.exists(path) or not os.path.isdir(path):
        abort(404)
    page = request.args.get("page", 1, type=int)
    per_page = Config.ITEMS_PER_PAGE
    all_items = list_dir(path, subpath)
    total = len(all_items)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    items = all_items[start:start+per_page]
    return render_template("file_manage.html", items=items, subpath=subpath, page=page, total_pages=total_pages)

@admin_bp.route('/upload_file', methods=['POST'])
@admin_req
def admin_upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        return redirect("/admin/manage_files")
    if not is_allowed_file(file.filename, is_admin=True):
        return "文件类型不被允许", 400
    header = file.read(32)
    file.seek(0)
    kind = filetype.guess(header)
    ext = os.path.splitext(file.filename)[1].lower().lstrip('.')
    if kind is not None and kind.extension != ext:
        if not (ext in ('docx', 'xlsx', 'pptx') and kind.extension == 'zip'):
            return "文件内容与扩展名不符", 400
    subpath = request.form.get("subpath", "").strip()
    target_dir = safe_path(Config.SHARE_DIR, subpath) if subpath else Config.SHARE_DIR
    fn = secure_filename(file.filename)
    dest = unique_path(target_dir, fn)
    file.save(dest)
    target = f"/admin/manage_files/{subpath}" if subpath else "/admin/manage_files"
    return redirect(target)

@admin_bp.route('/move_file', methods=['POST'])
@admin_req
def move_file():
    source_path = request.form.get("source_path", "").strip()
    target_folder = request.form.get("target_folder", "").strip()
    if not source_path:
        return "源文件路径不能为空", 400
    src = safe_path(Config.SHARE_DIR, source_path)
    if not os.path.isfile(src):
        return "源文件不存在", 404
    if target_folder:
        dest_dir = safe_path(Config.SHARE_DIR, target_folder)
    else:
        dest_dir = Config.SHARE_DIR
    os.makedirs(dest_dir, exist_ok=True)
    fname = os.path.basename(src)
    dest = unique_path(dest_dir, fname)
    shutil.move(src, dest)
    logging.info(f"文件移动: {src} -> {dest}")
    source_dir = os.path.dirname(source_path)
    target = f"/admin/manage_files/{source_dir}" if source_dir else "/admin/manage_files"
    return redirect(target)

@admin_bp.route('/delete_file', methods=['POST'])
@admin_req
def admin_delete_file():
    p = request.form.get("path", "")
    fp = safe_path(Config.SHARE_DIR, p)
    if os.path.isfile(fp):
        move_trash(fp, p)
        audit_log.info(f"管理员 {session['admin_username']} 删除了文件: {p}")
    return redirect(request.referrer or "/admin/manage_files")

@admin_bp.route('/pending_files')
@admin_req
def pending_files():
    files = [{"name": n, "size": f"{os.path.getsize(os.path.join(Config.UPLOAD_PENDING_DIR, n))/1024:.1f} KB"}
             for n in os.listdir(Config.UPLOAD_PENDING_DIR) if os.path.isfile(os.path.join(Config.UPLOAD_PENDING_DIR, n))]
    return render_template("pending_files.html", files=files, dirs=all_dirs(Config.SHARE_DIR))

@admin_bp.route('/approve_file', methods=['POST'])
@admin_req
def approve_file():
    fn = request.form.get("filename", "")
    target = os.path.normpath(request.form.get("target_folder", "").strip())
    if target == ".": target = ""
    dest_dir = safe_path(Config.SHARE_DIR, target) if target else Config.SHARE_DIR
    src = os.path.join(Config.UPLOAD_PENDING_DIR, fn)
    oname = fn.split("_", 1)[1] if "_" in fn else fn
    dest = unique_path(dest_dir, oname)
    if os.path.isfile(src):
        shutil.move(src, dest)
        audit_log.info(f"批准文件: {fn} -> {dest}")
    return redirect("/admin/pending_files")

@admin_bp.route('/reject_file', methods=['POST'])
@admin_req
def reject_file():
    fn = request.form.get("filename", "")
    fp = os.path.join(Config.UPLOAD_PENDING_DIR, fn)
    if os.path.isfile(fp):
        move_trash(fp)
        audit_log.info(f"拒绝文件: {fn}")
    return redirect("/admin/pending_files")

@admin_bp.route('/trash')
@admin_req
def view_trash():
    items = []
    for root, _, files in os.walk(Config.TRASH_DIR):
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, Config.TRASH_DIR)
            items.append({"name": name, "original_path": rel, "size": f"{os.path.getsize(path)/1024:.1f} KB", "current_path": rel})
    return render_template("trash.html", items=items)

@admin_bp.route('/trash/restore', methods=['POST'])
@admin_req
def restore_trash():
    cur = request.form.get("current_path", "")
    fn = request.form.get("filename", "")
    src = safe_path(Config.TRASH_DIR, cur)
    if not os.path.isfile(src):
        return "不存在", 404
    rel_dir = os.path.dirname(cur)
    target = Config.SHARE_DIR if not rel_dir else safe_path(Config.SHARE_DIR, rel_dir)
    os.makedirs(target, exist_ok=True)
    dest = unique_path(target, fn)
    shutil.move(src, dest)
    audit_log.info(f"恢复文件: {src} -> {dest}")
    return redirect("/admin/trash")

@admin_bp.route('/trash/delete', methods=['POST'])
@admin_req
def delete_trash():
    cur = request.form.get("current_path", "")
    fp = safe_path(Config.TRASH_DIR, cur)
    if os.path.isfile(fp):
        os.remove(fp)
        audit_log.info(f"永久删除文件: {fp}")
    return redirect("/admin/trash")

# ==================== 文章审核 ====================
@admin_bp.route('/approve_articles')
@admin_req
def art_approval():
    db = get_db()
    articles = []
    for r in db.execute("SELECT id, title, author, category, content FROM pending_articles WHERE is_draft = 0 ORDER BY time DESC"):
        excerpt = r["content"][:150].replace("\n", " ") + ("..." if len(r["content"]) > 150 else "")
        articles.append({"id": r["id"], "title": r["title"], "author": r["author"], "category": r["category"], "excerpt": excerpt})
    return render_template("art_approval.html", articles=articles)

@admin_bp.route('/preview_article/<aid>')
@admin_req
def preview_pending_article(aid):
    db = get_db()
    row = db.execute("SELECT title, author, time, category, content FROM pending_articles WHERE id = ?", (aid,)).fetchone()
    if not row:
        abort(404)
    content = render_article_content(row["content"])
    return render_template("pending_article_view.html", title=row["title"], author=row["author"],
                           time=row["time"], category=row["category"], content=content)

@admin_bp.route('/approve_article', methods=['POST'])
@admin_req
def approve_article():
    aid = request.form.get("article_id", "")
    db = get_db()
    row = db.execute("SELECT title, author, time, category, content FROM pending_articles WHERE id = ?", (aid,)).fetchone()
    if row:
        db.execute("INSERT INTO articles (id, title, author, time, category, content) VALUES (?, ?, ?, ?, ?, ?)",
                   (aid, row["title"], row["author"], row["time"], row["category"], row["content"]))
        tags = db.execute("SELECT tag FROM article_tags WHERE article_id = ?", (aid,)).fetchall()
        for t in tags:
            db.execute("INSERT INTO article_tags (article_id, tag) VALUES (?, ?)", (aid, t["tag"]))
        db.execute("DELETE FROM pending_articles WHERE id = ?", (aid,))
        db.commit()
        author_email = db.execute("SELECT email FROM authors WHERE username = ?", (row["author"],)).fetchone()
        if author_email and author_email["email"]:
            subject = f"您的文章《{row['title']}》已通过审核"
            body = f"<p>尊敬的 {row['author']}，</p><p>您的文章《<strong>{row['title']}</strong>》已通过审核并发布。</p><p><a href='/news/{aid}'>点击查看</a></p>"
            send_email(author_email["email"], subject, body)
        audit_log.info(f"文章审核通过: {aid} 作者 {row['author']}")
    return redirect("/admin/approve_articles")

@admin_bp.route('/reject_article', methods=['POST'])
@admin_req
def reject_article():
    aid = request.form.get("article_id", "")
    db = get_db()
    row = db.execute("SELECT title, author FROM pending_articles WHERE id = ?", (aid,)).fetchone()
    if row:
        author_email = db.execute("SELECT email FROM authors WHERE username = ?", (row["author"],)).fetchone()
        if author_email and author_email["email"]:
            subject = f"您的文章《{row['title']}》未通过审核"
            body = f"<p>尊敬的 {row['author']}，</p><p>您的文章《<strong>{row['title']}</strong>》未通过审核。请修改后重新投稿。</p>"
            send_email(author_email["email"], subject, body)
        db.execute("DELETE FROM pending_articles WHERE id = ?", (aid,))
        db.commit()
    return redirect("/admin/approve_articles")

# ==================== 作者审核 ====================
@admin_bp.route('/approve_authors')
@admin_req
def author_approval():
    db = get_db()
    pend = [{"username": r["username"], "email": r["email"]} for r in db.execute("SELECT username, email FROM pending_authors")]
    return render_template("auth_approval.html", pending_authors=pend)

@admin_bp.route('/approve_author', methods=['POST'])
@admin_req
def approve_author():
    u = request.form.get("username", "").strip()
    db = get_db()
    row = db.execute("SELECT password, email FROM pending_authors WHERE username = ?", (u,)).fetchone()
    if row:
        db.execute("INSERT INTO authors (username, password, email) VALUES (?, ?, ?)", (u, row["password"], row["email"]))
        db.execute("DELETE FROM pending_authors WHERE username = ?", (u,))
        db.commit()
        if row["email"]:
            subject = "作者注册审核通过"
            body = f"<p>尊敬的 {u}，</p><p>您的作者账号已通过审核，现在可以登录并发表文章了。</p><p><a href='/author/login'>登录</a></p>"
            send_email(row["email"], subject, body)
        audit_log.info(f"批准作者: {u}")
    return redirect("/admin/approve_authors")

@admin_bp.route('/reject_author', methods=['POST'])
@admin_req
def reject_author():
    u = request.form.get("username", "").strip()
    db = get_db()
    row = db.execute("SELECT email FROM pending_authors WHERE username = ?", (u,)).fetchone()
    if row and row["email"]:
        subject = "作者注册审核未通过"
        body = f"<p>尊敬的 {u}，</p><p>您的作者注册申请未通过审核。如有疑问请联系管理员。</p>"
        send_email(row["email"], subject, body)
    db.execute("DELETE FROM pending_authors WHERE username = ?", (u,))
    db.commit()
    return redirect("/admin/approve_authors")

# ==================== 作者管理 ====================
@admin_bp.route('/manage_authors')
@admin_req
def manage_authors():
    db = get_db()
    authors = [r["username"] for r in db.execute("SELECT username FROM authors")]
    return render_template("author_manage.html", authors=authors)

@admin_bp.route('/delete_author', methods=['POST'])
@admin_req
def delete_author():
    u = request.form.get("username", "").strip()
    db = get_db()
    db.execute("DELETE FROM comments WHERE author = ?", (u,))
    db.execute("DELETE FROM article_likes WHERE user = ?", (u,))
    db.execute("DELETE FROM article_tags WHERE article_id IN (SELECT id FROM articles WHERE author = ?)", (u,))
    db.execute("DELETE FROM article_tags WHERE article_id IN (SELECT id FROM pending_articles WHERE author = ?)", (u,))
    db.execute("DELETE FROM articles WHERE author = ?", (u,))
    db.execute("DELETE FROM pending_articles WHERE author = ?", (u,))
    db.execute("DELETE FROM authors WHERE username = ?", (u,))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 删除了作者: {u}")
    return redirect("/admin/manage_authors")

# ==================== 已发布文章管理 ====================
@admin_bp.route('/manage_articles')
@admin_req
def manage_articles():
    db = get_db()
    articles = [{"id": r["id"], "title": r["title"], "author": r["author"], "time": r["time"],
                 "view_count": r["view_count"], "likes": r["likes"], "sticky": r["sticky"]}
                for r in db.execute("SELECT id, title, author, time, view_count, likes, sticky FROM articles ORDER BY sticky DESC, time DESC")]
    return render_template("article_manage.html", articles=articles)

@admin_bp.route('/delete_article_manage', methods=['POST'])
@admin_req
def delete_article_manage():
    aid = request.form.get("article_id", "")
    db = get_db()
    db.execute("DELETE FROM articles WHERE id = ?", (aid,))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 删除了文章: {aid}")
    return redirect("/admin/manage_articles")

@admin_bp.route('/toggle_sticky/<aid>')
@admin_req
def toggle_sticky(aid):
    db = get_db()
    row = db.execute("SELECT sticky FROM articles WHERE id = ?", (aid,)).fetchone()
    if row:
        new_sticky = 0 if row["sticky"] else 1
        db.execute("UPDATE articles SET sticky = ? WHERE id = ?", (new_sticky, aid))
        db.commit()
        audit_log.info(f"管理员 {session['admin_username']} 修改文章 {aid} 置顶状态为 {new_sticky}")
    return redirect("/admin/manage_articles")

# ==================== 编辑文章 ====================
@admin_bp.route('/edit_article/<aid>', methods=['GET', 'POST'])
@admin_req
def edit_article(aid):
    db = get_db()
    row = db.execute("SELECT title, category, content FROM articles WHERE id = ?", (aid,)).fetchone()
    location = "articles"
    if not row:
        row = db.execute("SELECT title, category, content FROM pending_articles WHERE id = ?", (aid,)).fetchone()
        location = "pending_articles"
    if not row:
        abort(404)
    article = {"title": row["title"], "category": row["category"], "content": row["content"]}
    tags = [t["tag"] for t in db.execute("SELECT tag FROM article_tags WHERE article_id = ?", (aid,)).fetchall()]
    error = None
    msg = None
    if request.method == "POST":
        new_title = request.form.get("title", "").strip()
        new_cat = request.form.get("category", "key")
        new_content = request.form.get("content", "").strip()
        tags_str = request.form.get("tags", "").strip()
        if not new_title or not new_content:
            error = "标题和内容不能为空"
        else:
            if location == "articles":
                db.execute("UPDATE articles SET title = ?, category = ?, content = ?, updated_at = ? WHERE id = ?",
                           (new_title, new_cat, new_content, time.strftime("%Y-%m-%d %H:%M"), aid))
            else:
                db.execute("UPDATE pending_articles SET title = ?, category = ?, content = ? WHERE id = ?",
                           (new_title, new_cat, new_content, aid))
            db.execute("DELETE FROM article_tags WHERE article_id = ?", (aid,))
            if tags_str:
                for tag in tags_str.split(",")[:5]:
                    if tag.strip():
                        db.execute("INSERT INTO article_tags (article_id, tag) VALUES (?, ?)", (aid, tag.strip()))
            db.commit()
            msg = "文章已更新"
    return render_template("edit_article.html", article=article, tags=tags, error=error, msg=msg,
                           back_url="/admin/manage_articles", can_internal=True)

# ==================== 聊天用户管理 ====================
@admin_bp.route('/chat_users')
@admin_req
def chat_users():
    db = get_db()
    users = [r["username"] for r in db.execute("SELECT username FROM chat_users")]
    return render_template("chat_user_manage.html", users=users)

@admin_bp.route('/chat_users/delete', methods=['POST'])
@admin_req
def delete_chat_user():
    username = request.form.get("username", "").strip()
    db = get_db()
    db.execute("DELETE FROM chat_messages WHERE user = ?", (username,))
    db.execute("DELETE FROM chat_users WHERE username = ?", (username,))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 删除了聊天用户: {username}")
    return redirect("/admin/chat_users")

@admin_bp.route('/chat_messages')
@admin_req
def chat_messages():
    db = get_db()
    messages = [{"id": r["id"], "user": r["user"], "text": r["text"], "time": r["time"]}
                for r in db.execute("SELECT id, user, text, time FROM chat_messages ORDER BY id DESC LIMIT 200")]
    return render_template("chat_messages_manage.html", messages=messages)

@admin_bp.route('/chat_messages/delete', methods=['POST'])
@admin_req
def delete_chat_message():
    msg_id = request.form.get("message_id", "")
    db = get_db()
    db.execute("DELETE FROM chat_messages WHERE id = ?", (msg_id,))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 删除了聊天消息 {msg_id}")
    return redirect("/admin/chat_messages")

# ==================== 系统设置 ====================
@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_req
def settings():
    db = get_db()
    if request.method == "POST":
        reg_enabled = "true" if request.form.get("registration_enabled") == "on" else "false"
        captcha_type = request.form.get("captcha_type", "math")
        email_enabled = "true" if request.form.get("email_enabled") == "on" else "false"
        smtp_server = request.form.get("smtp_server", "").strip()
        smtp_port = request.form.get("smtp_port", "587").strip()
        smtp_user = request.form.get("smtp_user", "").strip()
        smtp_password = request.form.get("smtp_password", "").strip()
        notify_email = request.form.get("notify_email", "").strip()
        db.execute("UPDATE site_config SET value = ? WHERE key = 'registration_enabled'", (reg_enabled,))
        db.execute("UPDATE site_config SET value = ? WHERE key = 'captcha_type'", (captcha_type,))
        db.execute("UPDATE site_config SET value = ? WHERE key = 'email_enabled'", (email_enabled,))
        db.execute("UPDATE site_config SET value = ? WHERE key = 'smtp_server'", (smtp_server,))
        db.execute("UPDATE site_config SET value = ? WHERE key = 'smtp_port'", (smtp_port,))
        db.execute("UPDATE site_config SET value = ? WHERE key = 'smtp_user'", (smtp_user,))
        if smtp_password:
            db.execute("UPDATE site_config SET value = ? WHERE key = 'smtp_password'", (smtp_password,))
        db.execute("UPDATE site_config SET value = ? WHERE key = 'notify_email'", (notify_email,))
        db.commit()
        audit_log.info(f"管理员 {session['admin_username']} 修改了系统设置")
        return redirect("/admin/settings")
    config = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM site_config").fetchall()}
    return render_template("settings.html",
                           reg_enabled=config.get("registration_enabled") == "true",
                           captcha_type=config.get("captcha_type", "math"),
                           email_enabled=config.get("email_enabled") == "true",
                           smtp_server=config.get("smtp_server", ""),
                           smtp_port=config.get("smtp_port", "587"),
                           smtp_user=config.get("smtp_user", ""),
                           smtp_password="",
                           notify_email=config.get("notify_email", ""))

# ==================== 审计日志 ====================
@admin_bp.route('/audit_log')
@admin_req
def audit_log_view():
    if not os.path.exists("audit.log"):
        return "日志文件不存在"
    with open("audit.log", "r") as f:
        log_content = f.read()
    return render_template("audit_log.html", log_content=log_content)

# ==================== 重置用户密码 ====================
@admin_bp.route('/reset_user_password', methods=['POST'])
@admin_req
def reset_user_password():
    u = request.form.get("username", "").strip()
    utype = request.form.get("usertype", "")
    table_map = {"authors": "authors", "admins": "admins", "chat_users": "chat_users"}
    if utype not in table_map:
        return "参数错误", 400
    if utype == "admins":
        db = get_db()
        current_role = db.execute("SELECT role FROM admins WHERE username = ?", (session["admin_username"],)).fetchone()["role"]
        if current_role != "super":
            return "仅超级管理员可重置其他管理员密码", 403
    table = table_map[utype]
    db = get_db()
    if not db.execute(f"SELECT username FROM {table} WHERE username = ?", (u,)).fetchone():
        return "用户不存在", 404
    new_pwd = secrets.token_hex(4)
    hashed = generate_password_hash(new_pwd)
    db.execute(f"UPDATE {table} SET password = ? WHERE username = ?", (hashed, u))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 重置了 {utype} 用户 {u} 的密码")
    return f"""<html><body style="font-family:system-ui;text-align:center;padding:40px">
    <h2>密码已重置</h2><p>用户 <strong>{_html.escape(u)}</strong> 的新密码为：</p>
    <h3 style="color:#b22222" id="newPwd">{_html.escape(new_pwd)}</h3>
    <button onclick="copyPwd()" style="padding:10px 20px;background:#b22222;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:1rem">📋 复制密码</button>
    <p>请立即通知该用户使用此密码登录并修改密码。</p>
    <script>
    function copyPwd() {{
        const pwd = document.getElementById('newPwd').innerText;
        navigator.clipboard.writeText(pwd).then(() => {{
            alert('密码已复制到剪贴板！');
        }}).catch(() => {{
            prompt('请手动复制密码:', pwd);
        }});
    }}
    </script>
    </body></html>"""

# ==================== 作者内部权限管理 ====================
@admin_bp.route('/author_permissions')
@admin_req
def author_permissions():
    db = get_db()
    authors = [{"username": r["username"], "can_access": bool(r["can_access_internal"])}
               for r in db.execute("SELECT username, can_access_internal FROM authors")]
    return render_template("author_permission.html", authors=authors)

@admin_bp.route('/grant_internal', methods=['POST'])
@admin_req
def grant_internal():
    u = request.form.get("username", "").strip()
    db = get_db()
    db.execute("UPDATE authors SET can_access_internal = 1 WHERE username = ?", (u,))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 授予 {u} 内部权限")
    return redirect("/admin/author_permissions")

@admin_bp.route('/revoke_internal', methods=['POST'])
@admin_req
def revoke_internal():
    u = request.form.get("username", "").strip()
    db = get_db()
    db.execute("UPDATE authors SET can_access_internal = 0 WHERE username = ?", (u,))
    db.commit()
    audit_log.info(f"管理员 {session['admin_username']} 撤销 {u} 内部权限")
    return redirect("/admin/author_permissions")