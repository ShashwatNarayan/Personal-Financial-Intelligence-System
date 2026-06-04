from flask import Flask, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day"])
csrf = CSRFProtect()


def create_app(config_object='config.Config'):
    app = Flask(__name__, template_folder='templates')
    app.config.from_object(config_object)

    # pool_pre_ping handles Neon cold-start reconnects; recycle aligns with Neon's idle timeout
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_size': 5,
        'pool_recycle': 300,
        'connect_args': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000'
        }
    }

    CORS(app)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    from app.api import api_bp
    app.register_blueprint(api_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.main import main_bp
    app.register_blueprint(main_bp)

    from app.ai import ai_bp
    app.register_blueprint(ai_bp)

    from app.cli import deduplicate_cmd, clear_data_cmd
    app.cli.add_command(deduplicate_cmd)
    app.cli.add_command(clear_data_cmd)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'status': 'error', 'message': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'status': 'error', 'message': 'Server error'}), 500

    return app
