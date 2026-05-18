# 🌐 万象门户 · 多功能内容管理平台
# Vientiane Portal - Multi-functional Content Management Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Flask-2.3.3-red.svg" alt="Flask">
  <img src="https://img.shields.io/badge/Socket.IO-5.3.4-yellow.svg" alt="Socket.IO">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg" alt="Platform">
</p>

<p align="center">
  <strong>集文件共享、文章发布、实时聊天、管理后台于一体的综合型 Web 应用</strong>
  <br>
  <em>An integrated web application with file sharing, article publishing, real-time chat and admin backend</em>
</p>

<details>
<summary><strong>🇨🇳 中文介绍 · Click to expand</strong></summary>

## ✨ 核心特性

| 功能 | 说明 |
| :--- | :--- |
| 📂 **资源万象站** | 多格式文件在线预览（PDF、图片、音视频、Office、CHM、DjVu、文本）、目录浏览、分页、打包下载 |
| 🔗 **文件分享** | 生成带密码和过期时间的分享链接，支持提取码验证 |
| 📰 **新闻栏（文章系统）** | 作者投稿、读者评论/点赞、管理员审核；支持 Markdown、标签、置顶、收藏、内部文章权限 |
| 💬 **聊天室** | Socket.IO 实时消息，5 分钟内可撤回，@提及通知，头像系统，消息保留 200 条 |
| 🔐 **管理员后台** | 仪表盘统计、文章/作者审核、文件管理、回收站、聊天管理、系统设置、审计日志 |
| 🧩 **通用安全** | CSRF Token、CSP 策略、登录限流（5 次失败锁 15 分钟）、文件类型校验、HTML 清洗 |
| 🌙 **暗色模式** | 前端本地存储，一键切换亮色/暗色主题 |
| 🌐 **HTTPS 强制** | 通过环境变量 `FORCE_HTTPS=1` 开启，配合 Nginx 代理 |

## 🚀 快速启动

### 1. 环境准备
- Python 3.8+
- 安装系统依赖（可选，用于增强预览）：
  ```bash
  # Ubuntu/Debian
  apt install -y libchm-bin djvulibre-bin
  ```

### 2. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

### 3. 设置环境变量（可选）
```bash
export SECRET_KEY="your_secret_key"
export FORCE_HTTPS=0
export DEFAULT_ADMIN_PWD=""
```

### 4. 启动服务
```bash
python app.py
```
默认监听 `[::]:8080`（IPv6 + IPv4）。访问 `http://localhost:8080` 即可。

### 5. 使用 HTTPS + Nginx 代理（推荐生产环境）
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    # SSL 证书配置...
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 📁 项目结构

```
├── app.py                 # 主入口，注册蓝图、启动服务、CSRF/CSP 中间件
├── config.py              # 全局配置（路径、扩展名、分页、预览类型）
├── models.py              # 数据库表定义与初始化
├── utils.py               # 通用工具（验证码、限流、密码哈希、安全路径、审计日志）
├── file_indexer.py        # 文本文件内容索引（FTS5）与 watchdog 实时监控
├── requirements.txt       # Python 依赖
├── blueprints/
│   ├── __init__.py        # 蓝图注册
│   ├── admin.py           # 管理员后台
│   ├── author.py          # 作者模块
│   ├── chat.py            # 聊天室（Socket.IO 事件）
│   ├── files.py           # 文件浏览、预览、上传、分享链接
│   └── news.py            # 文章广场、内部文章
├── templates/             # 所有 HTML 模板（需从 app.txt 常量中提取）
├── shared_files/          # 共享文件根目录（自动创建）
├── uploads_pending/       # 待审核文件临时目录
├── trash/                 # 回收站
├── avatars/               # 用户头像
├── data.db                # SQLite 数据库
└── audit.log              # 审计日志
```

> **模板文件说明**：所有 HTML 模板内容原存放于 `app.txt` 中的常量（如 `INDEX_HTML`、`FILES_HTML` 等）。您需要将这些常量分别保存为 `templates/` 下对应的文件名（参考蓝图中的 `render_template` 调用名称），或直接运行旧版单文件模式。

## ⚙️ 重要配置

| 配置项 | 说明 | 位置 |
|--------|------|------|
| `MAX_CONTENT_LENGTH` | 最大上传大小（默认 30GB） | `config.py` |
| `ITEMS_PER_PAGE` | 文件列表分页大小（默认 20） | `config.py` |
| `ARTICLES_PER_PAGE` | 文章列表分页大小（默认 10） | `config.py` |
| `ALLOWED_EXTENSIONS` | 普通用户允许上传的扩展名 | `config.py` |
| `ADMIN_ALLOWED_EXTENSIONS` | 管理员允许上传的扩展名 | `config.py` |
| 邮件通知 | SMTP 服务器、端口、用户名、密码 | 后台系统设置 |
| 注册开关 | 是否允许新用户注册 | 后台系统设置 |

## 🔒 安全要点

- ✅ 所有 POST 请求均需携带 CSRF Token（部分公开接口除外）
- ✅ 登录失败 5 次即锁定 15 分钟（基于 IP）
- ✅ 密码存储使用 Werkzeug 的 `generate_password_hash`（bcrypt 或 pbkdf2）
- ✅ 支持旧 SHA256 哈希自动升级为安全哈希
- ✅ 文件上传通过 `filetype` 校验真实类型，防止伪造 MIME
- ✅ 文章内容经 Bleach 清洗，防止 XSS 攻击
- ✅ CSP 内容安全策略限制脚本和样式来源
- ✅ 强制 HTTPS 选项（生产环境推荐开启）

## 🧪 扩展建议

- **生产环境**：使用 `eventlet` 或 `gunicorn + gevent` 提高并发性能
- **数据库**：将 SQLite 替换为 PostgreSQL（需改写 `get_db` 和部分查询）
- **文件存储**：增加对象存储（如 MinIO、OSS）替代本地存储
- **会话管理**：使用 Redis 管理 Socket.IO 会话（多进程部署）
- **日志监控**：集成 Sentry 或 ELK 进行错误跟踪

## 📄 许可证

本项目采用 [MIT License](LICENSE)，欢迎自由使用、修改和分发。

</details>

<details>
<summary><strong>🇬🇧 English · Click to expand</strong></summary>

## ✨ Core Features

| Feature | Description |
| :--- | :--- |
| 📂 **File Center** | Online preview of various formats (PDF, images, audio/video, Office, CHM, DjVu, text), directory browsing, pagination, folder ZIP download |
| 🔗 **File Sharing** | Create share links with password & expiration, password-protected downloads |
| 📰 **Article System** | Authors submit, readers comment/like, admin approval; Markdown, tags, sticky, bookmarks, internal articles with separate permission |
| 💬 **Chat Room** | Real-time messaging via Socket.IO, message recall (5 min), @mentions, avatars, last 200 messages kept |
| 🔐 **Admin Panel** | Dashboard stats, article/author approval, file management, trash, chat management, system settings, audit log |
| 🧩 **Security** | CSRF token, CSP headers, login throttling (5 fails lock 15 min), file type validation, HTML sanitization |
| 🌙 **Dark Mode** | LocalStorage toggle, one‑click switch |
| 🌐 **HTTPS Enforce** | Enabled via `FORCE_HTTPS=1`, works with Nginx reverse proxy |

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8+
- Install system dependencies (optional, for enhanced preview):
  ```bash
  # Ubuntu/Debian
  apt install -y libchm-bin djvulibre-bin
  ```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Set environment variables (optional)
```bash
export SECRET_KEY="your_secret_key"
export FORCE_HTTPS=0
export DEFAULT_ADMIN_PWD=""
```

### 4. Start the server
```bash
python app.py
```
Default listens on `[::]:8080` (IPv6 + IPv4). Visit `http://localhost:8080`.

### 5. Use HTTPS + Nginx (recommended for production)
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    # SSL certificate configuration...
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 📁 Project Structure

```
├── app.py                 # Main entry, blueprint registration, CSRF/CSP middleware
├── config.py              # Global configuration (paths, extensions, pagination)
├── models.py              # Database table definitions & initialization
├── utils.py               # Utilities (captcha, throttling, password hashing, safe path, audit log)
├── file_indexer.py        # Text file indexing (FTS5) + watchdog monitor
├── requirements.txt       # Python dependencies
├── blueprints/
│   ├── __init__.py        # Blueprint registration
│   ├── admin.py           # Admin backend
│   ├── author.py          # Author module
│   ├── chat.py            # Chat room (Socket.IO events)
│   ├── files.py           # File browsing, preview, upload, share links
│   └── news.py            # Article list, internal articles, comments
├── templates/             # All HTML templates (extract from app.txt constants)
├── shared_files/          # Shared files root (auto-created)
├── uploads_pending/       # Pending file uploads
├── trash/                 # Recycle bin
├── avatars/               # User avatars
├── data.db                # SQLite database
└── audit.log              # Audit log
```

> **Template note**: All HTML templates are originally embedded as constants in `app.txt` (e.g., `INDEX_HTML`, `FILES_HTML`). You need to extract them into `templates/` with the corresponding filenames (refer to `render_template` calls in blueprints), or run the original single‑file version.

## ⚙️ Configuration

| Option | Description | Location |
|--------|-------------|----------|
| `MAX_CONTENT_LENGTH` | Max upload size (default 30GB) | `config.py` |
| `ITEMS_PER_PAGE` | Files per page (default 20) | `config.py` |
| `ARTICLES_PER_PAGE` | Articles per page (default 10) | `config.py` |
| `ALLOWED_EXTENSIONS` | Extensions allowed for guests | `config.py` |
| `ADMIN_ALLOWED_EXTENSIONS` | Extensions allowed for admins | `config.py` |
| Email notification | SMTP server, port, user, password | Admin backend settings |
| Registration toggle | Enable/disable new user registration | Admin backend settings |

## 🔒 Security Highlights

- ✅ All POST requests require CSRF token (except whitelisted endpoints)
- ✅ 5 failed logins → 15 minutes lock (IP‑based)
- ✅ Passwords hashed with Werkzeug (bcrypt/pbkdf2)
- ✅ Legacy SHA256 hashes automatically upgraded
- ✅ File uploads validated by `filetype` (MIME mismatch rejection)
- ✅ Article content sanitized with Bleach (XSS protection)
- ✅ CSP headers restrict script/style sources
- ✅ Optional HTTPS enforcement (`FORCE_HTTPS=1`)

## 🧪 Extension Suggestions

- **Production**：Use `eventlet` or `gunicorn + gevent` for higher concurrency
- **Database**：Replace SQLite with PostgreSQL (rewrite `get_db` & queries)
- **File storage**：Add object storage (MinIO, OSS) instead of local disk
- **Session management**：Use Redis for Socket.IO (multi‑process deployment)
- **Monitoring**：Integrate Sentry or ELK for error tracking

## 📄 License

This project is open‑sourced under the [MIT License](LICENSE). Feel free to use, modify, and distribute.

</details>