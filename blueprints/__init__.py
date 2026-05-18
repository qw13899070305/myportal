from .admin import admin_bp
from .author import author_bp
from .chat import chat_bp
from .files import files_bp
from .news import news_bp

def register_blueprints(app, socketio):
    app.register_blueprint(admin_bp)
    app.register_blueprint(author_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(news_bp)
    # 将 socketio 实例传递给需要的蓝图（例如聊天室）
    from .chat import set_socketio
    set_socketio(socketio)