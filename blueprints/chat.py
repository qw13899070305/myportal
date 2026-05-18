from flask import Blueprint, render_template, request, redirect, session, jsonify
from flask_socketio import emit
import re
from datetime import datetime
from config import Config
from utils import chat_req, get_db, verify_pw, generate_password_hash, is_strong_password, audit_log
import os

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')
socketio = None

def set_socketio(sio):
    global socketio
    socketio = sio
    # 在 socketio 初始化后注册事件
    register_socketio_events()

def register_socketio_events():
    """在 socketio 对象可用后注册事件处理函数"""
    if socketio is None:
        return

    @socketio.on('join')
    def handle_join(data):
        username = data.get("username", "").strip() or session.get("chat_username")
        if not username:
            return
        db = get_db()
        c = db.cursor()
        c.execute("SELECT id, user, text, time, can_edit FROM chat_messages ORDER BY id DESC LIMIT 50")
        rows = c.fetchall()
        messages = []
        for r in reversed(rows):
            short_time = r[3][-8:-3] if len(r[3]) >= 16 else r[3]
            messages.append({"id": r[0], "user": r[1], "text": r[2], "time": short_time, "can_edit": bool(r[4])})
        emit("load_messages", messages)

    @socketio.on('send_message')
    def handle_message(data):
        username = data.get("username", "").strip() or session.get("chat_username")
        if not username:
            return
        text = data.get("text", "").strip()[:500]
        if not text:
            return
        now = datetime.now()
        msg_time_full = now.strftime("%Y-%m-%d %H:%M:%S")
        msg_time_short = now.strftime("%H:%M:%S")
        db = get_db()
        c = db.cursor()
        c.execute("INSERT INTO chat_messages (user, text, time, can_edit) VALUES (?, ?, ?, 1)",
                  (username, text, msg_time_full))
        msg_id = c.lastrowid
        c.execute("DELETE FROM chat_messages WHERE id NOT IN (SELECT id FROM chat_messages ORDER BY id DESC LIMIT 200)")
        db.commit()
        mentions = re.findall(r'@(\w+)', text)
        for mentioned_user in set(mentions):
            if mentioned_user != username:
                db.execute("INSERT INTO notifications (username, content, time) VALUES (?, ?, ?)",
                           (mentioned_user, f"{username} 在聊天室提到了你", msg_time_full))
        db.commit()
        socketio.emit("chat_message", {"id": msg_id, "user": username, "text": text,
                                       "time": msg_time_short, "can_edit": True}, broadcast=True)

# ==================== 页面路由 ====================
@chat_bp.route('/')
def index():
    if not session.get("chat_username"):
        return redirect("/chat/login")
    return render_template("chat_room.html")

@chat_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get("chat_username"):
        return redirect("/chat")
    err = None
    next_url = request.args.get("next", "/chat")
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        db = get_db()
        row = db.execute("SELECT password FROM chat_users WHERE username = ?", (u,)).fetchone()
        if not row or not verify_pw(row["password"], p, "chat_users", u):
            err = "用户名或密码错误"
        else:
            session.permanent = True
            session["chat_username"] = u
            return redirect(next_url)
    return render_template("chat_login.html", error=err)

@chat_bp.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db()
    reg_enabled = db.execute("SELECT value FROM site_config WHERE key = 'registration_enabled'").fetchone()["value"] == "true"
    if not reg_enabled:
        return "管理员已关闭新用户注册", 403
    err = None
    next_url = request.args.get("next", "/chat")
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if not u or not p:
            err = "请填写完整信息"
        elif not is_strong_password(p):
            err = "密码强度不足（至少8位，含大小写字母和数字）"
        elif db.execute("SELECT username FROM chat_users WHERE username = ?", (u,)).fetchone():
            err = "用户名已存在"
        else:
            db.execute("INSERT INTO chat_users (username, password) VALUES (?, ?)", (u, generate_password_hash(p)))
            db.commit()
            audit_log.info(f"聊天用户注册: {u}")
            session.permanent = True
            session["chat_username"] = u
            return redirect(next_url)
    return render_template("chat_reg.html", error=err)

@chat_bp.route('/logout')
def logout():
    session.pop("chat_username", None)
    return redirect("/")

@chat_bp.route('/upload_avatar', methods=['GET', 'POST'])
@chat_req
def upload_avatar():
    username = session["chat_username"]
    if request.method == "POST":
        file = request.files.get("avatar")
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                import filetype
                header = file.read(32)
                file.seek(0)
                kind = filetype.guess(header)
                if kind is None or kind.extension not in ['jpg', 'jpeg', 'png', 'gif']:
                    return "无效的图片文件，请上传真正的 JPG/PNG/GIF", 400
                filename = f"{username}{ext}"
                filepath = os.path.join(Config.AVATARS_DIR, filename)
                file.save(filepath)
                db = get_db()
                db.execute("UPDATE chat_users SET avatar = ? WHERE username = ?", (f"/avatars/{filename}", username))
                db.commit()
                audit_log.info(f"聊天用户 {username} 更新了头像")
                return redirect("/chat")
    avatar_url = f"/avatar/{username}"
    return render_template("upload_avatar.html", avatar_url=avatar_url, back_url="/chat")

@chat_bp.route('/revoke', methods=['POST'])
def revoke_message():
    if not session.get("chat_username"):
        return jsonify({"success": False}), 403
    data = request.get_json()
    msg_id = data.get("message_id")
    db = get_db()
    row = db.execute("SELECT user, time, can_edit FROM chat_messages WHERE id = ?", (msg_id,)).fetchone()
    if row and row["user"] == session["chat_username"] and row["can_edit"] == 1:
        try:
            msg_time = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - msg_time).total_seconds() <= 300:
                db.execute("UPDATE chat_messages SET text = '消息已撤回', can_edit = 0 WHERE id = ?", (msg_id,))
                db.commit()
                short_time = row["time"][-8:-3]
                socketio.emit("chat_message", {"id": msg_id, "user": row["user"], "text": "消息已撤回",
                                               "time": short_time, "can_edit": False}, broadcast=True)
                return jsonify({"success": True})
        except:
            pass
    return jsonify({"success": False})