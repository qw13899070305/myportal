import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "a1b2c3d4e5f6g7h8i9j0klmnopqrstuv"
    MAX_CONTENT_LENGTH = 30 * 1024 * 1024 * 1024  # 30GB
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 86400  # 24小时
    FORCE_HTTPS = os.environ.get("FORCE_HTTPS") == "1"

    # 分页设置
    ITEMS_PER_PAGE = 20
    ARTICLES_PER_PAGE = 10

    # 文件目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "data.db")
    SHARE_DIR = os.path.join(BASE_DIR, "shared_files")
    UPLOAD_PENDING_DIR = os.path.join(BASE_DIR, "uploads_pending")
    TRASH_DIR = os.path.join(BASE_DIR, "trash")
    AVATARS_DIR = os.path.join(BASE_DIR, "avatars")

    # 允许的文件扩展名
    ALLOWED_EXTENSIONS = {'.jpg','.jpeg','.png','.gif','.webp','.mp4','.webm','.mov','.mp3','.ogg','.wav','.pdf','.txt','.md','.zip','.docx','.xlsx','.pptx','.doc','.xls','.ppt'}
    ADMIN_ALLOWED_EXTENSIONS = ALLOWED_EXTENSIONS | {'.py','.c','.cpp','.html','.css','.js','.json','.xml','.csv','.log','.yaml','.yml','.ini','.conf','.sh','.bat','.ps1','.r','.swift','.kt','.go','.rs','.php','.rb','.pl','.lua','.scala','.hs','.erl','.exs','.dart','.vue','.jsx','.tsx','.svelte'}

    # 预览类型
    VIDEO = {".mp4",".webm",".mov",".mkv",".avi",".flv",".wmv",".m4v",".mpg",".mpeg",".3gp",".ogv",".ts"}
    AUDIO = {".mp3",".ogg",".wav",".flac",".m4a",".aac",".wma",".opus",".mid",".midi",".aiff",".alac"}
    IMAGE = {".jpg",".jpeg",".png",".gif",".svg",".webp",".bmp",".ico",".tiff",".tif",".heic",".heif",".avif"}
    TEXT = {".txt",".md",".py",".java",".c",".cpp",".h",".html",".htm",".css",".js",".ts",".json",".xml",".csv",".log",".yaml",".yml",".ini",".cfg",".conf",".sh",".bat",".ps1",".toml",".rst",".tex",".bib",".sql",".r",".swift",".kt",".go",".rs",".php",".rb",".pl",".lua",".scala",".hs",".erl",".ex",".exs",".dart",".vue",".jsx",".tsx",".svelte"}
    OFFICE = {".docx",".xlsx",".pptx"}
    OLD_OFFICE = {".doc",".xls",".ppt"}
    DJVU = {".djvu",".djv"}
    CHM = {".chm"}
    PREVIEW = VIDEO | AUDIO | IMAGE | {".pdf"} | TEXT | OFFICE | OLD_OFFICE | DJVU | CHM