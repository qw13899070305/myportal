from flask import Blueprint, render_template, request, redirect, session, jsonify, abort
import time
from config import Config
from utils import get_db, render_article_content, internal_req

news_bp = Blueprint('news', __name__, url_prefix='/news')

# ==================== 公开文章列表 ====================
@news_bp.route('/')
def index():
    page = request.args.get("page", 1, type=int)
    per_page = Config.ARTICLES_PER_PAGE
    search = request.args.get("q", "").strip()
    db = get_db()
    if search:
        rows = db.execute("SELECT rowid, title, author, time, category, content, view_count, likes FROM articles_fts WHERE articles_fts MATCH ? AND category != 'internal' ORDER BY rowid DESC LIMIT ? OFFSET ?",
                          (search, per_page, (page-1)*per_page)).fetchall()
        article_ids = [r["rowid"] for r in rows]
        if article_ids:
            placeholders = ','.join('?' * len(article_ids))
            articles = db.execute(f"SELECT id, title, author, time, category, content, view_count, likes FROM articles WHERE rowid IN ({placeholders}) AND category != 'internal' ORDER BY sticky DESC, time DESC",
                                  article_ids).fetchall()
            total = db.execute("SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH ? AND category != 'internal'", (search,)).fetchone()[0]
        else:
            articles = []
            total = 0
    else:
        articles = db.execute("SELECT id, title, author, time, category, content, view_count, likes FROM articles WHERE category != 'internal' ORDER BY sticky DESC, time DESC LIMIT ? OFFSET ?",
                              (per_page, (page-1)*per_page)).fetchall()
        total = db.execute("SELECT COUNT(*) FROM articles WHERE category != 'internal'").fetchone()[0]
    total_pages = (total + per_page - 1) // per_page
    arts = []
    for a in articles:
        excerpt = a["content"][:100].replace("\n", " ")
        if len(a["content"]) > 100:
            excerpt += "..."
        tags = [t["tag"] for t in db.execute("SELECT tag FROM article_tags WHERE article_id = ?", (a["id"],)).fetchall()]
        arts.append({"id": a["id"], "title": a["title"], "author": a["author"], "time": a["time"],
                     "category": a["category"], "excerpt": excerpt, "view_count": a["view_count"],
                     "likes": a["likes"], "tags": tags})
    return render_template("news.html", articles=arts, page=page, total_pages=total_pages,
                           search_query=search, is_internal=False)

# ==================== 查看文章 ====================
@news_bp.route('/<aid>')
def view(aid):
    db = get_db()
    row = db.execute("SELECT title, author, time, category, content, view_count, likes FROM articles WHERE id = ?", (aid,)).fetchone()
    if not row:
        abort(404)
    if row["category"] == "internal":
        if not (session.get("admin_username") or (session.get("author_username") and db.execute("SELECT can_access_internal FROM authors WHERE username = ?", (session["author_username"],)).fetchone()["can_access_internal"] == 1)):
            return redirect(f"/internal/login?next=/news/{aid}")
    db.execute("UPDATE articles SET view_count = view_count + 1 WHERE id = ?", (aid,))
    db.commit()
    tags = [t["tag"] for t in db.execute("SELECT tag FROM article_tags WHERE article_id = ?", (aid,)).fetchall()]
    comments = db.execute("SELECT id, author, content, time, likes FROM comments WHERE article_id = ? ORDER BY id DESC", (aid,)).fetchall()
    content = render_article_content(row["content"])
    return render_template("article_view.html", title=row["title"], author=row["author"], time=row["time"],
                           category=row["category"], content=content, comments=comments, aid=aid,
                           view_count=row["view_count"]+1, like_count=row["likes"], tags=tags)

# ==================== 点赞 ====================
@news_bp.route('/<aid>/like', methods=['POST'])
def like(aid):
    if not session.get("author_username") and not session.get("chat_username"):
        return jsonify({"success": False, "error": "请先登录"}), 403
    user = session.get("author_username") or session.get("chat_username")
    db = get_db()
    existing = db.execute("SELECT 1 FROM article_likes WHERE article_id = ? AND user = ?", (aid, user)).fetchone()
    if existing:
        db.execute("DELETE FROM article_likes WHERE article_id = ? AND user = ?", (aid, user))
        db.execute("UPDATE articles SET likes = likes - 1 WHERE id = ?", (aid,))
        db.commit()
        new_likes = db.execute("SELECT likes FROM articles WHERE id = ?", (aid,)).fetchone()["likes"]
        return jsonify({"success": True, "likes": new_likes, "liked": False})
    else:
        db.execute("INSERT INTO article_likes (article_id, user) VALUES (?, ?)", (aid, user))
        db.execute("UPDATE articles SET likes = likes + 1 WHERE id = ?", (aid,))
        db.commit()
        new_likes = db.execute("SELECT likes FROM articles WHERE id = ?", (aid,)).fetchone()["likes"]
        return jsonify({"success": True, "likes": new_likes, "liked": True})

# ==================== 收藏 ====================
@news_bp.route('/<aid>/bookmark', methods=['POST'])
def bookmark(aid):
    if not session.get("author_username") and not session.get("chat_username"):
        return jsonify({"success": False, "message": "请先登录"}), 403
    user = session.get("author_username") or session.get("chat_username")
    db = get_db()
    existing = db.execute("SELECT 1 FROM article_bookmarks WHERE article_id = ? AND user = ?", (aid, user)).fetchone()
    if existing:
        db.execute("DELETE FROM article_bookmarks WHERE article_id = ? AND user = ?", (aid, user))
        db.commit()
        return jsonify({"success": True, "message": "已取消收藏"})
    else:
        db.execute("INSERT INTO article_bookmarks (article_id, user) VALUES (?, ?)", (aid, user))
        db.commit()
        return jsonify({"success": True, "message": "已收藏"})

# ==================== 发表评论 ====================
@news_bp.route('/<aid>/comment', methods=['POST'])
def comment(aid):
    if not session.get("author_username") and not session.get("chat_username"):
        return "请登录后评论", 403
    author = session.get("author_username") or session.get("chat_username")
    content = request.form.get("content", "").strip()
    if not content:
        return "内容不能为空", 400
    if len(content) > 1000:
        return "评论过长", 400
    db = get_db()
    db.execute("INSERT INTO comments (article_id, author, content, time) VALUES (?, ?, ?, ?)",
               (aid, author, content, time.strftime("%Y-%m-%d %H:%M")))
    db.commit()
    return redirect(f"/news/{aid}")

# ==================== 评论点赞 ====================
@news_bp.route('/comment/<cid>/like', methods=['POST'])
def like_comment(cid):
    if not session.get("author_username") and not session.get("chat_username"):
        return jsonify({"success": False}), 403
    user = session.get("author_username") or session.get("chat_username")
    db = get_db()
    existing = db.execute("SELECT 1 FROM comment_likes WHERE comment_id = ? AND user = ?", (cid, user)).fetchone()
    if existing:
        db.execute("DELETE FROM comment_likes WHERE comment_id = ? AND user = ?", (cid, user))
        db.execute("UPDATE comments SET likes = likes - 1 WHERE id = ?", (cid,))
    else:
        db.execute("INSERT INTO comment_likes (comment_id, user) VALUES (?, ?)", (cid, user))
        db.execute("UPDATE comments SET likes = likes + 1 WHERE id = ?", (cid,))
    db.commit()
    return jsonify({"success": True})

# ==================== 内部文章列表 ====================
@news_bp.route('/internal')
@internal_req
def internal():
    page = request.args.get("page", 1, type=int)
    per_page = Config.ARTICLES_PER_PAGE
    search = request.args.get("q", "").strip()
    db = get_db()
    if search:
        rows = db.execute("SELECT rowid, title, author, time, category, content, view_count, likes FROM articles_fts WHERE articles_fts MATCH ? AND category = 'internal' ORDER BY rowid DESC LIMIT ? OFFSET ?",
                          (search, per_page, (page-1)*per_page)).fetchall()
        article_ids = [r["rowid"] for r in rows]
        if article_ids:
            placeholders = ','.join('?' * len(article_ids))
            articles = db.execute(f"SELECT id, title, author, time, category, content, view_count, likes FROM articles WHERE rowid IN ({placeholders}) AND category = 'internal' ORDER BY sticky DESC, time DESC",
                                  article_ids).fetchall()
            total = db.execute("SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH ? AND category = 'internal'", (search,)).fetchone()[0]
        else:
            articles = []
            total = 0
    else:
        articles = db.execute("SELECT id, title, author, time, category, content, view_count, likes FROM articles WHERE category = 'internal' ORDER BY sticky DESC, time DESC LIMIT ? OFFSET ?",
                              (per_page, (page-1)*per_page)).fetchall()
        total = db.execute("SELECT COUNT(*) FROM articles WHERE category = 'internal'").fetchone()[0]
    total_pages = (total + per_page - 1) // per_page
    arts = []
    for a in articles:
        excerpt = a["content"][:100].replace("\n", " ")
        if len(a["content"]) > 100:
            excerpt += "..."
        tags = [t["tag"] for t in db.execute("SELECT tag FROM article_tags WHERE article_id = ?", (a["id"],)).fetchall()]
        arts.append({"id": a["id"], "title": a["title"], "author": a["author"], "time": a["time"],
                     "category": a["category"], "excerpt": excerpt, "view_count": a["view_count"],
                     "likes": a["likes"], "tags": tags})
    return render_template("news.html", articles=arts, page=page, total_pages=total_pages,
                           search_query=search, is_internal=True)

# ==================== 内部文章查看 ====================
@news_bp.route('/internal/<aid>')
@internal_req
def view_internal(aid):
    return view(aid)