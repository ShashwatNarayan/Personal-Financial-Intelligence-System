from flask import Blueprint

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')

from app.ai import routes  # noqa: F401, E402
