"""
Celestial Platform — app.py
"""
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
import os

from database import init_db
from config import Config

# Blueprint imports
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.client import client_bp
from routes.pm import pm_bp
from routes.gm import gm_bp
from routes.tl import tl_bp
from routes.member import member_bp
from routes.freelancer import freelancer_bp
from routes.accountant import accountant_bp
from routes.bank import bank_bp
from routes.shared import shared_bp

socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

def create_app(config_class=Config):
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app = Flask(__name__, static_folder=base_dir, static_url_path='')
    app.config.from_object(config_class)
    
    CORS(app, supports_credentials=True)
    socketio.init_app(app, manage_session=False)

    # Register Socket handlers
    try:
        from routes.socket_events import register_socket_handlers
        register_socket_handlers(socketio)
    except Exception as e:
        print("⚠️ Socket events:", e)

    # Database
    with app.app_context():
        init_db()

    # Blueprints
    blueprints = [auth_bp, admin_bp, client_bp, pm_bp, gm_bp, tl_bp,
                  member_bp, freelancer_bp, accountant_bp, bank_bp, shared_bp]
    for bp in blueprints:
        app.register_blueprint(bp, url_prefix='/api')

    # Serve Frontend
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, 'index.html')

    return app


if __name__ == '__main__':
    app = create_app()
    print("[Celestial] Platform Started -> http://localhost:5000")
    print("[Celestial] Real-time notifications ACTIVE")
    socketio.run(app, debug=True, port=5000, host='0.0.0.0', allow_unsafe_werkzeug=True)