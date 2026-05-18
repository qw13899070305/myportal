# 万象门户 · 多功能内容管理平台
# Vientiane Portal - Multi-functional Content Management Platform

> 一个集文件共享、文章发布、实时聊天、管理后台于一体的综合型 Web 应用
> An integrated web application with file sharing, article publishing, real-time chat and admin backend

## 主要功能 | Features

### 资源万象站（文件中心）| File Center
- 多格式文件在线预览（PDF、图片、音视频、Office文档、CHM、DjVu、纯文本等）
- Online preview of various formats: PDF, images, audio/video, Office, CHM, DjVu, plain text...
- 目录浏览与面包屑导航，支持分页
- Directory browsing with breadcrumb navigation and pagination
- 文件上传（游客需验证码，管理员可批量审批）
- File upload (captcha for guests, admin approval for files)
- 生成分享链接（可设置密码、过期时间）
- Generate share links with password & expiration
- 全文搜索（对文本类文件内容建立FTS5索引）
- Full-text search inside text files (FTS5 index)
- 文件夹打包下载为ZIP
- Download folders as ZIP
- 管理员文件管理（移动、删除、恢复、彻底删除）
- Admin file management: move, delete, restore, permanent delete

### 新闻栏（文章系统）| Articles
- 多角色：作者（投稿）、读者（评论/点赞）、管理员（审核/管理）
- Multi-role: authors (submit), readers (comment/like), admins (approve/manage)
- 文章分类：重点新闻、娱乐区、内部文章（需授权访问）
- Categories: news, entertainment, internal (requires permission)
- Markdown支持（配合Bleach安全过滤）
- Markdown support with Bleach sanitizer
- 文章置顶、点赞、收藏、标签系统
- Sticky, likes, bookmarks, tags
- 嵌套评论 + 评论点赞
- Nested comments with comment likes
- 作者后台：文章列表、草稿箱、自动保存草稿、编辑资料、上传头像
- Author dashboard: articles, drafts, autosave, profile, avatar
- 邮件通知（审核通过/拒绝时自动发送）
- Email notification on approval/rejection
- 内部文章权限单独授予
- Internal article permission can be granted separately

### 聊天室（实时交流）| Chat Room
- 基于Socket.IO的实时消息
- Real-time messaging via Socket.IO
- 消息撤回（5分钟内可撤回）
- Message recall within 5 minutes
- @提及通知（生成系统通知）
- @mention notifications
- 用户头像（自动生成字母头像或自定义上传）
- Avatar: auto-generated or custom upload
- 消息记录保留最近200条
- Keep last 200 messages
- 管理员可管理聊天用户及消息
- Admin can manage users & messages

### 管理员后台 | Admin Panel
- 仪表盘统计（文章数、待审数、用户数）
- Dashboard statistics: articles, pending, users
- 文章审核（预览、通过、拒绝）
- Article approval: preview, approve, reject
- 作者审核（批准/拒绝注册申请）
- Author approval/denial
- 作者内部权限管理（授予/撤销访问内部文章的能力）
- Grant/revoke internal article access
- 文件管理（全目录浏览、上传、移动、删除、分享链接）
- Full file management: browse, upload, move, delete, share links
- 缓存区管理（回收站，可恢复或彻底删除）
- Trash management: restore or permanent delete
- 聊天用户与消息管理
- Chat users & messages management
- 管理员管理（超级管理员可增删管理员）
- Admin management (super admin only)
- 系统设置（注册开关、验证码类型、SMTP邮件配置）
- System settings: registration, captcha type, SMTP
- 审计日志（记录关键操作）
- Audit log

### 通用特性 | Common Features
- 安全防护：CSRF Token、CSP、X-Frame-Options、登录限流
- Security: CSRF, CSP, X-Frame-Options, login throttling
- 验证码：算术验证码 / 简单字符串（可配置）
- Captcha: math or alphanumeric (configurable)
- HTTPS强制（环境变量 FORCE_HTTPS=1）
- Enforce HTTPS via FORCE_HTTPS=1
- 暗色模式（前端本地存储，一键切换）
- Dark mode (localStorage, one-click toggle)
- 响应式布局（移动端适配）
- Responsive design

## 技术栈 | Tech Stack

| 类别 | 技术 |
|------|------|
| 后端框架 | Flask 2.3.3 + Flask-SocketIO 5.3.4 |
| 实时通信 | Socket.IO（自动降级：eventlet → threading） |
| 数据库 | SQLite3 + FTS5 全文扩展 |
| 安全 | Werkzeug、bleach、secrets |
| 文件处理 | filetype、zipfile、docx-preview / SheetJS |
| 后台任务 | threading + watchdog |
| 邮件 | smtplib（TLS） |
| 前端 | 原生HTML/CSS/JS |

## 项目结构 | Project Structure

```
├── app.py                 # 主入口
├── config.py              # 统一配置
├── models.py              # 数据库模型
├── utils.py               # 通用工具
├── file_indexer.py        # 文件索引与监控
├── requirements.txt       # Python依赖
├── blueprints/
│   ├── __init__.py        # 蓝图注册
│   ├── admin.py           # 管理员后台
│   ├── author.py          # 作者模块
│   ├── chat.py            # 聊天室
│   ├── files.py           # 文件管理
│   └── news.py            # 文章系统
├── templates/             # HTML模板
├── shared_files/          # 共享文件根目录
├── uploads_pending/       # 待审文件临时目录
├── trash/                 # 回收站
├── avatars/               # 用户头像
├── data.db                # SQLite数据库
└── audit.log              # 审计日志
```

> 模板文件说明：所有HTML模板原存放于app.txt中的常量，需提取到templates/目录下。

## 快速部署 | Quick Deployment

1. 环境准备：Python 3.8+
   Prerequisites: Python 3.8+

2. 安装系统依赖（可选）：
   Install system dependencies (optional):
   ```bash
   apt install -y libchm-bin djvulibre-bin
   ```

3. 安装Python依赖：
   Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. 设置环境变量（可选）：
   Set environment variables (optional):
   ```bash
   export SECRET_KEY="your_secret_key"
   export FORCE_HTTPS=0
   export DEFAULT_ADMIN_PWD=""
   ```

5. 启动服务：
   Start the server:
   ```bash
   python app.py
   ```

6. 访问：http://你的IP:8080
   Access: http://your-ip:8080

## 重要配置 | Configuration

- 最大上传大小：`MAX_CONTENT_LENGTH`（默认30GB）
- 分页数量：`ITEMS_PER_PAGE`、`ARTICLES_PER_PAGE`
- 允许的文件类型：`ALLOWED_EXTENSIONS`、`ADMIN_ALLOWED_EXTENSIONS`
- 邮件通知：需在后台填写SMTP配置
- 注册开关：后台系统设置

## 安全要点 | Security Highlights

- 所有POST请求需CSRF Token
- 登录失败5次锁定15分钟（基于IP）
- 密码使用Werkzeug安全哈希
- 文件上传通过filetype校验真实类型
- 文章内容经Bleach清洗防XSS
- CSP内容安全策略
- 强制HTTPS选项

## 扩展建议 | Extension Suggestions

- 生产环境使用eventlet或gunicorn+gevent
- 替换SQLite为PostgreSQL
- 使用对象存储（MinIO/OSS）替代本地存储
- 使用Redis管理Socket.IO会话（多进程部署）

## 许可证 | License

本项目未附带明确许可证，建议您添加合适的开源许可证（如MIT、GPLv3）。

---

**万象门户** —— 让分享与思想自由流动。
**Vientiane Portal** —— Let sharing and ideas flow freely.