from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename          # 新增
import secrets
from datetime import datetime, timedelta            # 修改（原为 from datetime import timedelta）
from flask import Blueprint, render_template, send_file, abort, request, redirect, session, jsonify, after_this_request
import os, zipfile, tempfile, shutil, uuid, time, mimetypes, html as _html, subprocess
from config import Config
from utils import (safe_path, list_dir, crumbs, captcha, verify_captcha, check_ip_throttle,
                   record_ip_fail, reset_ip_throttle, is_allowed_file, unique_path, get_db,
                   audit_log, move_trash)
import filetype

files_bp = Blueprint('files', __name__, url_prefix='/files')

# ==================== 浏览与预览 ====================
@files_bp.route('/', defaults={'subpath': ''})
@files_bp.route('/<path:subpath>')
def browse(subpath):
    path = safe_path(Config.SHARE_DIR, subpath) if subpath else Config.SHARE_DIR
    if not os.path.exists(path):
        abort(404)
    if os.path.isdir(path):
        page = request.args.get("page", 1, type=int)
        per_page = Config.ITEMS_PER_PAGE
        all_items = list_dir(path, subpath)
        total = len(all_items)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        items = all_items[start:start+per_page]
        q, a = captcha()
        session["captcha_q"] = q
        session["captcha_a"] = a
        return render_template("files.html", items=items, breadcrumbs=crumbs(subpath),
                               captcha_question=q, page=page, total_pages=total_pages, subpath=subpath)
    if request.args.get("action") == "download":
        return send_file(path, as_attachment=True)

    ext = os.path.splitext(subpath)[1].lower()
    if ext in Config.DJVU:
        return redirect(f"/djvu_preview/{subpath}")
    if ext in Config.CHM:
        return redirect(f"/chm_preview/{subpath}")
    if ext in {".html", ".htm"}:
        return send_file(path, as_attachment=True)
    if ext == ".svg":
        return send_file(path, mimetype="image/svg+xml")
    if ext in Config.VIDEO:
        return send_file(path, mimetype=mimetypes.guess_type(path)[0] or "video/mp4")
    if ext in Config.AUDIO:
        return send_file(path, mimetype=mimetypes.guess_type(path)[0] or "audio/mpeg")
    if ext in Config.IMAGE:
        return send_file(path, mimetype=mimetypes.guess_type(path)[0] or "image/png")
    if ext == ".pdf":
        return send_file(path, mimetype="application/pdf")
    if ext in Config.TEXT:
        try:
            with open(path, encoding='utf-8') as f:
                txt = f.read()
            return f"<html><body><pre>{_html.escape(txt)}</pre><p><a href='/files/{subpath}?action=download'>下载</a></p></body></html>"
        except:
            pass
    if ext in Config.OFFICE or ext in Config.OLD_OFFICE:
        return redirect(f"/office_preview/{subpath}")
    if ext == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                files = z.namelist()
            return f"<h2>压缩包内容</h2><ul>{''.join(f'<li>{_html.escape(f)}</li>' for f in files)}</ul><p><a href='/files/'>⬅ 返回</a></p>"
        except:
            abort(500)
    response = send_file(path, as_attachment=False)
    response.headers['Content-Disposition'] = 'inline'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

# ==================== Office 预览 ====================
@files_bp.route('/office_preview/<path:subpath>')
def office_preview(subpath):
    path = safe_path(Config.SHARE_DIR, subpath)
    if not os.path.isfile(path):
        abort(404)
    ext = os.path.splitext(subpath)[1].lower()
    if ext not in Config.OFFICE and ext not in Config.OLD_OFFICE:
        abort(404)
    return render_template("office_preview.html", subpath=subpath, ext=ext)

# ==================== CHM 预览 ====================
@files_bp.route('/chm_preview/<path:subpath>')
def chm_preview(subpath):
    src_path = safe_path(Config.SHARE_DIR, subpath)
    if not os.path.isfile(src_path) or os.path.splitext(subpath)[1].lower() != ".chm":
        abort(404)
    if not shutil.which("extract_chmLib"):
        return "服务器未安装 CHM 预览工具，请<a href='/files/{}?action=download'>下载</a>查看".format(subpath), 503
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(["extract_chmLib", src_path, tmpdir], check=True, timeout=30)
            index = None
            for root, _, files in os.walk(tmpdir):
                for f in files:
                    if f.lower() == "index.html" or f.lower().endswith(".html"):
                        index = os.path.join(root, f)
                        break
                if index:
                    break
            if not index:
                file_list = []
                for root, _, files in os.walk(tmpdir):
                    for f in files:
                        file_list.append(os.path.relpath(os.path.join(root, f), tmpdir))
                return f"<html><body><h2>CHM 文件内容列表</h2><ul>{''.join(f'<li>{_html.escape(f)}</li>' for f in file_list)}</ul><p><a href='/files/{subpath}?action=download'>下载原文件</a></p></body></html>"
            with open(index, encoding='utf-8', errors='ignore') as f:
                return f.read()
        except subprocess.TimeoutExpired:
            return "预览超时，请<a href='/files/{}?action=download'>下载</a>查看".format(subpath), 500
        except Exception as e:
            return f"预览失败: {e}", 500

# ==================== DjVu 预览 ====================
@files_bp.route('/djvu_preview/<path:subpath>')
def djvu_preview(subpath):
    src_path = safe_path(Config.SHARE_DIR, subpath)
    if not os.path.isfile(src_path) or os.path.splitext(subpath)[1].lower() not in Config.DJVU:
        abort(404)
    if not shutil.which("ddjvu"):
        return "服务器未安装 DjVu 预览工具，请<a href='/files/{}?action=download'>下载</a>查看".format(subpath), 503
    tmp_pdf = tempfile.mktemp(suffix=".pdf")
    try:
        subprocess.run(["ddjvu", "-format=pdf", src_path, tmp_pdf], check=True, timeout=60)
        response = send_file(tmp_pdf, mimetype="application/pdf", as_attachment=False,
                             download_name=os.path.splitext(os.path.basename(subpath))[0] + ".pdf")
        response.headers['Content-Disposition'] = 'inline'
        return response
    except subprocess.TimeoutExpired:
        return "预览超时，请<a href='/files/{}?action=download'>下载</a>查看".format(subpath), 500
    except Exception as e:
        return f"预览失败: {e}", 500
    finally:
        if os.path.exists(tmp_pdf):
            os.remove(tmp_pdf)

# ==================== 文件上传 ====================
@files_bp.route('/upload', methods=['POST'])
def upload():
    ip = request.remote_addr
    allowed, remain = check_ip_throttle(ip)
    if not allowed:
        return f"请求过于频繁，请等待 {remain} 秒后再试", 429
    if not verify_captcha(request.form.get("captcha_answer", ""), session.get("captcha_a")):
        record_ip_fail(ip)
        q, a = captcha()
        session["captcha_q"], session["captcha_a"] = q, a
        return "验证码错误", 400
    session.pop("captcha_q", None)
    session.pop("captcha_a", None)
    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return redirect("/files/")
    for file in files:
        if file.filename == "":
            continue
        if not is_allowed_file(file.filename, is_admin=False):
            continue
        header = file.read(32)
        file.seek(0)
        kind = filetype.guess(header)
        ext = os.path.splitext(file.filename)[1].lower().lstrip('.')
        if kind is not None and kind.extension != ext:
            if not (ext in ('docx', 'xlsx', 'pptx') and kind.extension == 'zip'):
                continue
        name = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
        file.save(os.path.join(Config.UPLOAD_PENDING_DIR, name))
    reset_ip_throttle(ip)
    return redirect("/files/")

# ==================== 文件夹打包下载 ====================
@files_bp.route('/download_folder/<path:subpath>')
def download_folder(subpath):
    if subpath:
        src_dir = safe_path(Config.SHARE_DIR, subpath)
    else:
        src_dir = Config.SHARE_DIR
    if not os.path.isdir(src_dir):
        abort(404)
    zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(zip_fd)
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, src_dir)
                    zf.write(full_path, arcname)
        @after_this_request
        def cleanup(response):
            try:
                os.remove(zip_path)
            except Exception as e:
                import logging
                logging.warning(f"删除临时zip失败: {e}")
            return response
        return send_file(zip_path, as_attachment=True, download_name=f"{os.path.basename(src_dir)}.zip")
    except Exception as e:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        abort(500)

# ==================== 分享链接创建 ====================
@files_bp.route('/create_share_link', methods=['POST'])
def create_share_link():
    if not session.get("admin_username") and not session.get("author_username"):
        return jsonify({"success": False, "error": "请先登录"}), 403
    data = request.get_json()
    file_path = data.get("path")
    password = data.get("password", "")
    expire_hours = data.get("expire", "24")
    if not file_path:
        return jsonify({"success": False, "error": "路径缺失"}), 400
    full_path = safe_path(Config.SHARE_DIR, file_path)
    if not os.path.isfile(full_path):
        return jsonify({"success": False, "error": "文件不存在"}), 404
    token = secrets.token_urlsafe(16)
    expire_time = (datetime.now() + timedelta(hours=int(expire_hours))).strftime("%Y-%m-%d %H:%M:%S")
    hashed_pw = generate_password_hash(password) if password else ""
    db = get_db()
    db.execute("INSERT INTO shared_links (token, file_path, password, expire_time, created_at) VALUES (?, ?, ?, ?, ?)",
               (token, file_path, hashed_pw, expire_time, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()
    link = request.host_url + "share/" + token
    return jsonify({"success": True, "url": link})

# ==================== 分享访问 ====================
@files_bp.route('/share/<token>', methods=['GET', 'POST'])
def access_share(token):
    from datetime import datetime, timedelta
    from utils import share_attempts
    db = get_db()
    row = db.execute("SELECT file_path, password, expire_time FROM shared_links WHERE token = ?", (token,)).fetchone()
    if not row:
        return render_template("share_page.html", error="无效的分享链接")
    if datetime.now() > datetime.strptime(row["expire_time"], "%Y-%m-%d %H:%M:%S"):
        return render_template("share_page.html", error="分享链接已过期")
    if request.method == "POST":
        ip = request.remote_addr
        attempts = share_attempts.get(ip, {"count": 0, "lock_until": 0})
        if attempts["lock_until"] > time.time():
            return render_template("share_page.html", error=f"尝试次数过多，请等待 {int(attempts['lock_until']-time.time())} 秒后再试")
        if row["password"]:
            if not check_password_hash(row["password"], request.form.get("password", "")):
                attempts["count"] += 1
                if attempts["count"] >= 5:
                    attempts["lock_until"] = time.time() + 600
                share_attempts[ip] = attempts
                return render_template("share_page.html", error="提取密码错误", token=token, need_password=True)
        share_attempts.pop(ip, None)
        full_path = safe_path(Config.SHARE_DIR, row["file_path"])
        if not os.path.isfile(full_path):
            abort(404)
        return send_file(full_path, as_attachment=True)
    return render_template("share_page.html", token=token, filename=os.path.basename(row["file_path"]),
                           expire=row["expire_time"], need_password=bool(row["password"]))

# ==================== 文件内容搜索 ====================
@files_bp.route('/search')
def search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return redirect("/files")
    db = get_db()
    rows = db.execute(
        "SELECT path, snippet(file_texts_fts, 1, '<b>', '</b>', '', 32) as snippet "
        "FROM file_texts_fts WHERE file_texts_fts MATCH ? ORDER BY rank LIMIT 20",
        (q,)
    ).fetchall()
    results = [{"path": r["path"], "snippet": r["snippet"]} for r in rows]
    items = "".join(
        f'<li><a href="/files/{_html.escape(r["path"])}">{_html.escape(r["path"])}</a> — {r["snippet"]}</li>'
        for r in results
    )
    return f"<h2>文件内容搜索结果 ({len(results)})</h2><ul>{items}</ul><p><a href='/files/'>← 返回</a></p>"