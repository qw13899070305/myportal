from flask import Blueprint, render_template, request, redirect, session, jsonify, abort
import uuid, time
from config import Config
from utils import (author_req, get_db, is_strong_password, generate_password_hash,
                   verify_pw, send_email, audit_log, render_article_content)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

author_bp = Blueprint('author', __name__, url_prefix='/author')

# ==================== 登录/登出 ====================
@author_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get("author_username"):
        return redirect("/author/dashboard")
    err = None
    next_url = request.form.get("next") or request.args.get("next") or "/author/dashboard"
    is_internal = "/internal" in (next_url or "")
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        db = get_db()
        row = db.execute("SELECT password, email FROM authors WHERE username = ?", (u,)).fetchone()
        if not row or not verify_pw(row["password"], p, "authors", u):
            err = "用户名或密码错误"
            if is_internal:
                return render_template("internal_login.html", next=next_url, author_error=err, admin_error=None)
        else:
            session.permanent = True
            session["author_username"] = u
            session["author_email"] = row["email"]
            return redirect(next_url)
    return render_template("author_login.html", error=err, next=next_url)

@author_bp.route('/logout')
def logout():
    session.pop("author_username", None)
    session.pop("author_email", None)
    return redirect("/")

# ==================== 注册 ====================
@author_bp.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db()
    reg_enabled = db.execute("SELECT value FROM site_config WHERE key = 'registration_enabled'").fetchone()["value"] == "true"
    if not reg_enabled:
        return "管理员已关闭新用户注册", 403
    err = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        if not u or not p:
            err = "请填写完整信息"
        elif not is_strong_password(p):
            err = "密码强度不足（至少8位，含大小写字母和数字）"
        elif db.execute("SELECT username FROM authors WHERE username = ?", (u,)).fetchone():
            err = "用户名已存在"
        elif db.execute("SELECT username FROM pending_authors WHERE username = ?", (u,)).fetchone():
            err = "用户名已申请，等待审核"
        else:
            db.execute("INSERT INTO pending_authors (username, password, email) VALUES (?, ?, ?)",
                       (u, generate_password_hash(p), email))
            db.commit()
            audit_log.info(f"作者注册申请: {u}")
            return "✅ 注册已提交。<br><a href='/news'>返回</a>"
    return render_template("author_reg.html", error=err)

# ==================== 投稿 ====================
@author_bp.route('/write', methods=['GET', 'POST'])
@author_req
def write():
    username = session["author_username"]
    db = get_db()
    has_perm = db.execute("SELECT can_access_internal FROM authors WHERE username = ?", (username,)).fetchone()
    can_internal = has_perm["can_access_internal"] == 1 if has_perm else False
    if request.method == "POST":
        cat = request.form.get("category", "key")
        if cat == "internal" and not can_internal:
            return "您没有发布内部文章的权限", 403
        t = request.form.get("title", "").strip()
        c = request.form.get("content", "").strip()
        tags_str = request.form.get("tags", "").strip()
        is_draft = 1 if request.form.get("save_draft") else 0
        if not t or not c:
            return "标题和内容不能为空", 400
        if len(c) > 100000:
            return "内容过长", 400
        aid = uuid.uuid4().hex[:10]
        db.execute("INSERT INTO pending_articles (id, title, author, time, category, content, is_draft) VALUES (?,?,?,?,?,?,?)",
                   (aid, t, username, time.strftime("%Y-%m-%d %H:%M"), cat, c, is_draft))
        if tags_str:
            for tag in tags_str.split(",")[:5]:
                if tag.strip():
                    db.execute("INSERT INTO article_tags (article_id, tag) VALUES (?, ?)", (aid, tag.strip()))
        db.commit()
        if is_draft:
            return f"✅ 草稿已保存。<br><a href='/author/dashboard'>返回仪表盘</a> | <a href='/author/write'>继续写新文章</a>"
        else:
            return f"✅ 投稿成功。<br><a href='/author/dashboard'>返回仪表盘</a> | <a href='/news'>广场</a>"
    return render_template("write.html", can_internal=can_internal)

# ==================== 仪表盘 ====================
@author_bp.route('/dashboard')
@author_req
def dashboard():
    username = session["author_username"]
    db = get_db()
    published = [{"id": r["id"], "title": r["title"], "time": r["time"], "category": r["category"]}
                 for r in db.execute("SELECT id, title, time, category FROM articles WHERE author = ?", (username,))]
    pending = [{"id": r["id"], "title": r["title"], "time": r["time"], "category": r["category"]}
               for r in db.execute("SELECT id, title, time, category FROM pending_articles WHERE author = ? AND is_draft = 0", (username,))]
    drafts = [{"id": r["id"], "title": r["title"], "time": r["time"]}
              for r in db.execute("SELECT id, title, time FROM pending_articles WHERE author = ? AND is_draft = 1", (username,))]
    stats = {"total": len(published) + len(pending) + len(drafts),
             "published": len(published), "pending": len(pending), "drafts": len(drafts)}
    return render_template("author_dashboard.html", published=published, pending=pending, drafts=drafts, stats=stats)

# ==================== 头像上传 ====================
@author_bp.route('/upload_avatar', methods=['GET', 'POST'])
@author_req
def upload_avatar():
    username = session["author_username"]
    if request.method == "POST":
        file = request.files.get("avatar")
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                header = file.read(32)
                file.seek(0)
                import filetype
                kind = filetype.guess(header)
                if kind is None or kind.extension not in ['jpg', 'jpeg', 'png', 'gif']:
                    return "无效的图片文件，请上传真正的 JPG/PNG/GIF", 400
                filename = f"{username}{ext}"
                filepath = os.path.join(Config.AVATARS_DIR, filename)
                file.save(filepath)
                db = get_db()
                db.execute("UPDATE authors SET avatar = ? WHERE username = ?", (f"/avatars/{filename}", username))
                db.commit()
                audit_log.info(f"作者 {username} 更新了头像")
                return redirect("/author/dashboard")
    avatar_url = f"/avatar/{username}"
    return render_template("upload_avatar.html", avatar_url=avatar_url, back_url="/author/dashboard")

# ==================== 编辑资料 ====================
@author_bp.route('/edit_profile', methods=['GET', 'POST'])
@author_req
def edit_profile():
    username = session["author_username"]
    db = get_db()
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        db.execute("UPDATE authors SET email = ? WHERE username = ?", (email, username))
        db.commit()
        session["author_email"] = email
        return redirect("/author/dashboard")
    row = db.execute("SELECT email FROM authors WHERE username = ?", (username,)).fetchone()
    return render_template("edit_profile.html", email=row["email"], back_url="/author/dashboard")

# ==================== 编辑文章 ====================
@author_bp.route('/edit_article/<aid>', methods=['GET', 'POST'])
@author_req
def edit_article(aid):
    username = session["author_username"]
    db = get_db()
    row = db.execute("SELECT title, category, content, is_draft FROM pending_articles WHERE id = ? AND author = ?", (aid, username)).fetchone()
    location = "pending"
    if not row:
        row = db.execute("SELECT title, category, content FROM articles WHERE id = ? AND author = ?", (aid, username)).fetchone()
        location = "published"
    if not row:
        abort(404)
    article = {"title": row["title"], "category": row["category"], "content": row["content"]}
    has_perm = db.execute("SELECT can_access_internal FROM authors WHERE username = ?", (username,)).fetchone()
    can_internal = has_perm["can_access_internal"] == 1 if has_perm else False
    if article["category"] == "internal" and not can_internal:
        abort(403)
    tags = [t["tag"] for t in db.execute("SELECT tag FROM article_tags WHERE article_id = ?", (aid,)).fetchall()]
    error = None
    msg = None
    if request.method == "POST":
        new_title = request.form.get("title", "").strip()
        new_cat = request.form.get("category", "key")
        if new_cat == "internal" and not can_internal:
            return "您没有权限将此文章设为内部文章", 403
        new_content = request.form.get("content", "").strip()
        tags_str = request.form.get("tags", "").strip()
        if not new_title or not new_content:
            error = "标题和内容不能为空"
        else:
            if location == "published":
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
                           back_url="/author/dashboard", can_internal=can_internal)

# ==================== 草稿自动保存 ====================
@author_bp.route('/draft/autosave', methods=['POST'])
@author_req
def autosave_draft():
    data = request.get_json()
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    tags_str = data.get("tags", "").strip()
    if not title and not content:
        return jsonify({"success": False})
    username = session["author_username"]
    db = get_db()
    existing = db.execute("SELECT id FROM pending_articles WHERE author = ? AND is_draft = 1", (username,)).fetchone()
    if existing:
        draft_id = existing["id"]
        db.execute("UPDATE pending_articles SET title=?, content=?, time=?, category='key' WHERE id=?",
                   (title, content, time.strftime("%Y-%m-%d %H:%M"), draft_id))
    else:
        draft_id = uuid.uuid4().hex[:10]
        db.execute("INSERT INTO pending_articles (id, title, author, time, category, content, is_draft) VALUES (?,?,?,?,?,?,1)",
                   (draft_id, title, username, time.strftime("%Y-%m-%d %H:%M"), "key", content))
    db.execute("DELETE FROM article_tags WHERE article_id = ?", (draft_id,))
    if tags_str:
        for tag in tags_str.split(",")[:5]:
            if tag.strip():
                db.execute("INSERT INTO article_tags (article_id, tag) VALUES (?, ?)", (draft_id, tag.strip()))
    db.commit()
    return jsonify({"success": True, "draft_id": draft_id})