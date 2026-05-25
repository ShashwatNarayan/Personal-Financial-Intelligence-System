from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_object='config.Config'):
    app = Flask(__name__, template_folder='templates')
    app.config.from_object(config_object)

    CORS(app)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Temporary user_loader - will be replaced in Phase 2
    @login_manager.user_loader
    def load_user(user_id):
        return None

    from app.api import api_bp
    app.register_blueprint(api_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    @app.route('/')
    def landing():
        return render_template('landing.html')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    @app.route('/upload')
    def upload_page():
        return render_template('dashboard.html')

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'status': 'error', 'message': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'status': 'error', 'message': 'Server error'}), 500

    return app
