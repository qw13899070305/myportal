import os, re, random, time, secrets, hashlib, base64, io, html as _html
from functools import wraps
from datetime import datetime, timedelta
from flask import session, redirect, abort, g, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from cachetools import TTLCache
import filetype
import logging
from logging.handlers import RotatingFileHandler
from config import Config

# 审计日志配置（全局唯一）
audit_log = logging.getLogger("audit")
audit_handler = RotatingFileHandler("audit.log", maxBytes=10*1024*1024, backupCount=5)
audit_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
audit_log.addHandler(audit_handler)
audit_log.setLevel(logging.INFO)

# 限流缓存
login_fails = TTLCache(maxsize=1000, ttl=900)
share_attempts = TTLCache(maxsize=500, ttl=3600)

def get_db():
    from models import get_db as _get_db
    return _get_db()

def safe_path(*parts):
    from config import Config
    p = os.path.realpath(os.path.join(*parts))
    if not p.startswith(os.path.realpath(Config.BASE_DIR)):
        abort(403)
    return p

def is_allowed_file(filename, is_admin=False):
    ext = os.path.splitext(filename)[1].lower()
    allowed = Config.ADMIN_ALLOWED_EXTENSIONS if is_admin else Config.ALLOWED_EXTENSIONS
    return ext in allowed

def captcha():
    db = get_db()
    row = db.execute("SELECT value FROM site_config WHERE key = 'captcha_type'").fetchone()
    captcha_type = row["value"] if row else "math"
    if captcha_type == "math":
        a, b = random.randint(10, 99), random.randint(10, 99)
        if a < b:
            a, b = b, a
        op = random.choice("+-")
        result = a + b if op == "+" else a - b
        ts = int(time.time())
        return f"{a} {op} {b} = ?", f"{result}:{ts}"
    else:
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "".join(random.choices(chars, k=5))
        ts = int(time.time())
        return f"验证码: {code}", f"{code}:{ts}"

def verify_captcha(answer, stored):
    if not stored:
        return False
    try:
        expected, ts = stored.split(":")
        if time.time() - int(ts) > 300:
            return False
        return answer.strip().upper() == expected.upper()
    except:
        return False

def unique_path(directory, fname):
    dest = os.path.join(directory, fname)
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(fname)
    i = 1
    while os.path.exists(dest):
        dest = os.path.join(directory, f"{base}_{i}{ext}")
        i += 1
    return dest

def move_trash(src, rel=None):
    from config import Config
    if rel:
        if '..' in rel or rel.startswith('/'):
            abort(403)
        d = os.path.join(Config.TRASH_DIR, os.path.dirname(rel))
        d = os.path.realpath(d)
        if not d.startswith(os.path.realpath(Config.TRASH_DIR)):
            abort(403)
    else:
        d = Config.TRASH_DIR
    os.makedirs(d, exist_ok=True)
    dest = unique_path(d, os.path.basename(src))
    import shutil
    shutil.move(src, dest)
    return dest

def crumbs(sub):
    if not sub:
        return []
    parts = sub.split("/")
    c, acc = [], ""
    for p in parts:
        acc = os.path.join(acc, p) if acc else p
        c.append({"name": p, "path": acc})
    return c

def list_dir(directory, base=""):
    items = []
    if not os.path.isdir(directory):
        return items
    for name in sorted(os.listdir(directory)):
        full = os.path.join(directory, name)
        rel = os.path.join(base, name) if base else name
        if os.path.isdir(full):
            items.append({"name": name, "path": rel, "is_dir": True, "is_file": False,
                          "size": "-", "type": "文件夹", "icon": "📁", "can_preview": False})
        else:
            sz = f"{os.path.getsize(full)/1024:.1f} KB"
            ext = os.path.splitext(name)[1].lower()
            can = ext in Config.PREVIEW
            ico = "📎"
            if ext in Config.VIDEO:
                ico = "🎬"
            elif ext in Config.AUDIO:
                ico = "🎵"
            elif ext in Config.IMAGE:
                ico = "🖼️"
            elif ext == ".pdf":
                ico = "📄"
            elif ext in Config.DJVU:
                ico = "📖"
            elif ext in Config.CHM:
                ico = "📖"
            elif ext == ".zip":
                ico = "📦"
            elif ext in Config.TEXT:
                ico = "📝"
            elif ext in Config.OFFICE:
                ico = "📄"
            elif ext in Config.OLD_OFFICE:
                ico = "📃"
            items.append({"name": name, "path": rel, "is_dir": False, "is_file": True,
                          "size": sz, "type": ext[1:].upper() if ext else "FILE",
                          "icon": ico, "can_preview": can,
                          "is_office": (ext in Config.OFFICE or ext in Config.OLD_OFFICE)})
    return items

def all_dirs(directory, prefix=""):
    dirs = []
    try:
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            if os.path.isdir(full):
                rel = os.path.join(prefix, name) if prefix else name
                dirs.append(rel)
                dirs.extend(all_dirs(full, rel))
    except:
        pass
    return dirs

def verify_pw(stored, pw, user_type=None, username=None):
    if len(stored) == 64 and all(c in '0123456789abcdef' for c in stored):
        if hashlib.sha256(pw.encode()).hexdigest() == stored:
            if user_type and username:
                db = get_db()
                if user_type == "admins":
                    db.execute("UPDATE admins SET password = ? WHERE username = ?",
                               (generate_password_hash(pw), username))
                elif user_type == "authors":
                    db.execute("UPDATE authors SET password = ? WHERE username = ?",
                               (generate_password_hash(pw), username))
                elif user_type == "chat_users":
                    db.execute("UPDATE chat_users SET password = ? WHERE username = ?",
                               (generate_password_hash(pw), username))
                db.commit()
            return True
        return False
    return check_password_hash(stored, pw)

def render_article_content(content):
    try:
        import markdown, bleach
        html_body = markdown.markdown(content, extensions=['extra', 'codehilite'])
        allowed_tags = ['b', 'i', 'a', 'p', 'ul', 'ol', 'li', 'code', 'pre', 'span',
                        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'img']
        allowed_attrs = {'a': ['href', 'title'], 'img': ['src', 'alt']}
        safe_html = bleach.clean(html_body, tags=allowed_tags, attributes=allowed_attrs, strip=True)
        return safe_html
    except:
        escaped = _html.escape(content)
        bolded = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
        return bolded.replace("\n", "<br>")

def is_strong_password(pw):
    if len(pw) < 8 or len(pw) > 128:
        return False
    if not re.search(r"[A-Z]", pw):
        return False
    if not re.search(r"[a-z]", pw):
        return False
    if not re.search(r"[0-9]", pw):
        return False
    return True

def send_email(to, subject, body):
    db = get_db()
    enabled = db.execute("SELECT value FROM site_config WHERE key = 'email_enabled'").fetchone()
    if not enabled or enabled["value"] != "true":
        return False
    smtp_server = db.execute("SELECT value FROM site_config WHERE key = 'smtp_server'").fetchone()["value"]
    smtp_port = int(db.execute("SELECT value FROM site_config WHERE key = 'smtp_port'").fetchone()["value"])
    smtp_user = db.execute("SELECT value FROM site_config WHERE key = 'smtp_user'").fetchone()["value"]
    smtp_password = db.execute("SELECT value FROM site_config WHERE key = 'smtp_password'").fetchone()["value"]
    if not smtp_server or not smtp_user:
        return False
    try:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html", "utf-8"))
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logging.error(f"邮件发送失败: {e}")
        return False

def generate_avatar(username):
    letter = username[0].upper() if username else "?"
    colors = ["#FF6B6B","#4ECDC4","#45B7D1","#96CEB4","#FFEAA7","#DDA0DD","#98D8C8","#F7C59F"]
    color = colors[hash(username) % len(colors)]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="40" fill="{color}"/>
        <text x="40" y="52" font-size="36" text-anchor="middle" fill="white" font-family="Arial">{letter}</text>
    </svg>'''
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

def check_ip_throttle(ip):
    data = login_fails.get(ip)
    if not data:
        return True, 0
    if data.get("lock_until", 0) > time.time():
        return False, int(data["lock_until"] - time.time())
    return True, 0

def record_ip_fail(ip):
    data = login_fails.get(ip, {"count": 0, "lock_until": 0})
    data["count"] += 1
    if data["count"] >= 5:
        data["lock_until"] = time.time() + 900
    login_fails[ip] = data

def reset_ip_throttle(ip):
    login_fails.pop(ip, None)

# 装饰器
def admin_req(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_username"):
            return redirect("/admin/login")
        db = get_db()
        row = db.execute("SELECT username FROM admins WHERE username = ?", (session["admin_username"],)).fetchone()
        if not row:
            session.clear()
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated

def super_req(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_username"):
            return redirect("/admin/login")
        db = get_db()
        row = db.execute("SELECT role FROM admins WHERE username = ?", (session["admin_username"],)).fetchone()
        if not row or row["role"] != "super":
            return "仅超级管理员可用", 403
        return f(*args, **kwargs)
    return decorated

def author_req(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("author_username"):
            return redirect("/author/login")
        db = get_db()
        row = db.execute("SELECT username FROM authors WHERE username = ?", (session["author_username"],)).fetchone()
        if not row:
            session.clear()
            return redirect("/author/login")
        return f(*args, **kwargs)
    return decorated

def chat_req(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("chat_username"):
            return redirect("/chat/login")
        db = get_db()
        row = db.execute("SELECT username FROM chat_users WHERE username = ?", (session["chat_username"],)).fetchone()
        if not row:
            session.clear()
            return redirect("/chat/login")
        return f(*args, **kwargs)
    return decorated

def internal_req(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("admin_username"):
            return f(*args, **kwargs)
        if session.get("author_username"):
            db = get_db()
            row = db.execute("SELECT can_access_internal FROM authors WHERE username = ?",
                             (session["author_username"],)).fetchone()
            if row and row["can_access_internal"] == 1:
                return f(*args, **kwargs)
            return "您没有内部访问权限，请联系管理员获取权限。", 403
        return redirect(f"/internal/login?next={request.path}")
    return decorated