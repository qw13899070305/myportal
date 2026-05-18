import sqlite3
import os
from flask import g
from config import Config

def get_db():
    if 'db' not in g:
        try:
            g.db = sqlite3.connect(Config.DB_PATH, timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA journal_mode=WAL;")
            g.db.execute("PRAGMA foreign_keys = ON;")
        except sqlite3.Error as e:
            import logging
            logging.error(f"数据库连接失败: {e}")
            raise
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(Config.DB_PATH)
    c = db.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT NOT NULL, role TEXT DEFAULT 'admin', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_admins (username TEXT PRIMARY KEY, password TEXT NOT NULL, email TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS authors (username TEXT PRIMARY KEY, password TEXT NOT NULL, email TEXT, avatar TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, can_access_internal INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_authors (username TEXT PRIMARY KEY, password TEXT NOT NULL, email TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_users (username TEXT PRIMARY KEY, password TEXT NOT NULL, avatar TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS articles (id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL, time TEXT NOT NULL, updated_at TEXT, category TEXT NOT NULL, content TEXT NOT NULL, view_count INTEGER DEFAULT 0, sticky INTEGER DEFAULT 0, likes INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_articles (id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL, time TEXT NOT NULL, category TEXT NOT NULL, content TEXT NOT NULL, is_draft INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id TEXT NOT NULL, author TEXT NOT NULL, content TEXT NOT NULL, time TEXT NOT NULL, parent_id INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS comment_likes (comment_id INTEGER, user TEXT, PRIMARY KEY(comment_id, user))''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, text TEXT NOT NULL, time TEXT NOT NULL, can_edit INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS article_tags (article_id TEXT, tag TEXT, PRIMARY KEY(article_id, tag))''')
    c.execute('''CREATE TABLE IF NOT EXISTS article_likes (article_id TEXT, user TEXT, PRIMARY KEY(article_id, user))''')
    c.execute('''CREATE TABLE IF NOT EXISTS article_bookmarks (article_id TEXT, user TEXT, PRIMARY KEY(article_id, user))''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, content TEXT NOT NULL, time TEXT NOT NULL, is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shared_links (token TEXT PRIMARY KEY, file_path TEXT NOT NULL, password TEXT, expire_time TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS site_config (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_articles_sticky_time ON articles(sticky DESC, time DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_comments_article ON comments(article_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_time ON chat_messages(id DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_article_tags ON article_tags(tag)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(title, content, content=articles, content_rowid='rowid')")
    c.execute("CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN INSERT INTO articles_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content); END;")
    c.execute("CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN INSERT INTO articles_fts(articles_fts, rowid, title, content) VALUES('delete', old.rowid, old.title, old.content); END;")
    c.execute("CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN INSERT INTO articles_fts(articles_fts, rowid, title, content) VALUES('delete', old.rowid, old.title, old.content); INSERT INTO articles_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content); END;")
    c.execute("CREATE TABLE IF NOT EXISTS file_texts (path TEXT PRIMARY KEY, content TEXT)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS file_texts_fts USING fts5(path, content, content=file_texts, content_rowid='rowid')")
    c.execute("CREATE TRIGGER IF NOT EXISTS file_texts_ai AFTER INSERT ON file_texts BEGIN INSERT INTO file_texts_fts(rowid, path, content) VALUES (new.rowid, new.path, new.content); END;")
    c.execute("CREATE TRIGGER IF NOT EXISTS file_texts_ad AFTER DELETE ON file_texts BEGIN INSERT INTO file_texts_fts(file_texts_fts, rowid, path, content) VALUES('delete', old.rowid, old.path, old.content); END;")
    db.commit()
    c.execute("SELECT COUNT(*) FROM admins")
    if c.fetchone()[0] == 0:
        import secrets
        from werkzeug.security import generate_password_hash
        default_pwd = os.environ.get("DEFAULT_ADMIN_PWD") or secrets.token_hex(6)
        c.execute("INSERT INTO admins (username, password, role) VALUES (?, ?, ?)", ("fengjiahang", generate_password_hash(default_pwd), "super"))
        db.commit()
        import logging
        logging.info(f"默认超级管理员已创建，密码: {default_pwd}")
    default_config = [
        ("registration_enabled", "true"), ("captcha_type", "math"), ("email_enabled", "false"),
        ("smtp_server", ""), ("smtp_port", "587"), ("smtp_user", ""), ("smtp_password", ""), ("notify_email", "")
    ]
    for key, val in default_config:
        c.execute("INSERT OR IGNORE INTO site_config (key, value) VALUES (?, ?)", (key, val))
    db.commit()
    db.close()