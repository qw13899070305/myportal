# -*- coding: utf-8 -*-
import os, uuid, secrets, logging
from flask import Flask, g, session, request, abort, redirect, render_template, send_file
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from models import get_db, close_db, init_db
from utils import admin_req, captcha, verify_captcha, check_ip_throttle, record_ip_fail, reset_ip_throttle, audit_log
from blueprints import register_blueprints
from file_indexer import start_watcher, schedule_indexing, cleanup_temp
import threading

# 初始化 Flask
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# HTTPS 强制重定向
if Config.FORCE_HTTPS:
    app.config["SESSION_COOKIE_SECURE"] = True
    @app.before_request
    def https_redirect():
        if request.headers.get("X-Forwarded-Proto", "http") == "http":
            return redirect(request.url.replace("http://", "https://", 1), code=301)

# SocketIO - 自动选择可用模式（eventlet > gevent > threading）
# 在普通 Linux/Windows 上自动使用 eventlet（高性能），在 Termux/Android 上自动降级到 threading
try:
    import eventlet
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
except (ImportError, ValueError):
    # eventlet 不可用或不兼容时使用 threading 模式
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# 基本日志配置（通用日志）
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 数据库会话管理
app.teardown_appcontext(close_db)

# 注册蓝图
register_blueprints(app, socketio)

# CSRF 保护
@app.before_request
def generate_nonce():
    g.csp_nonce = secrets.token_hex(16)

@app.context_processor
def inject_csrf_and_nonce():
    if "csrf_token" not in session:
        session["csrf_token"] = uuid.uuid4().hex
    return dict(csrf_token=session["csrf_token"], csp_nonce=g.csp_nonce)

@app.before_request
def csrf_protect():
    if request.method == "POST":
        if request.path.startswith("/socket.io/"):
            return
        if request.path in {"/admin/login", "/author/login", "/author/register", "/apply_admin",
                            "/upload", "/chat/login", "/chat/register", "/author/draft/autosave"}:
            return
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            token = request.headers.get("X-CSRF-Token", "")
            if not token or token != session.get("csrf_token"):
                abort(403)
            return
        if session.get("csrf_token") != request.form.get("csrf_token"):
            abort(400)

@app.after_request
def security_headers(response):
    nonce = g.get('csp_nonce', '')
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'unsafe-eval' 'nonce-{nonce}' https://cdn.socket.io https://cdn.jsdelivr.net; "
        f"style-src 'self' 'nonce-{nonce}'; connect-src 'self' ws: wss: https://cdn.socket.io; img-src 'self' data:;"
    )
    return response

# 初始化数据库和目录
init_db()
for d in [Config.SHARE_DIR, Config.UPLOAD_PENDING_DIR, Config.TRASH_DIR, Config.AVATARS_DIR]:
    os.makedirs(d, exist_ok=True)

# 启动后台线程
threading.Thread(target=schedule_indexing, daemon=True).start()
threading.Thread(target=cleanup_temp, daemon=True).start()
threading.Thread(target=start_watcher, daemon=True).start()

# 首页路由
@app.route("/")
def index():
    from models import get_db
    db = get_db()
    config = db.execute("SELECT value FROM site_config WHERE key='notify_email'").fetchone()
    notify_email = config["value"] if config else ""
    return render_template("index.html", notify_email=notify_email)

# ==================== 头像路由 ====================
@app.route('/avatar/<username>')
def get_avatar(username):
    from models import get_db
    import os, base64, io
    from utils import generate_avatar
    db = get_db()
    row = db.execute("SELECT avatar FROM authors WHERE username = ?", (username,)).fetchone()
    if row and row["avatar"] and os.path.exists(os.path.join(Config.BASE_DIR, row["avatar"].lstrip("/"))):
        return send_file(os.path.join(Config.BASE_DIR, row["avatar"].lstrip("/")), mimetype="image/jpeg")
    row = db.execute("SELECT avatar FROM chat_users WHERE username = ?", (username,)).fetchone()
    if row and row["avatar"] and os.path.exists(os.path.join(Config.BASE_DIR, row["avatar"].lstrip("/"))):
        return send_file(os.path.join(Config.BASE_DIR, row["avatar"].lstrip("/")), mimetype="image/jpeg")
    svg = generate_avatar(username)
    return send_file(io.BytesIO(base64.b64decode(svg.split(",")[1])), mimetype="image/svg+xml")

if __name__ == "__main__":
    socketio.run(app, host="::", port=8080, debug=False)