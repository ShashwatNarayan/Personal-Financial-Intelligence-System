import time
from collections import defaultdict, deque

from flask import current_app, jsonify, request
from flask_login import current_user, login_required

from app.ai import ai_bp
from app.ai.query_engine import (
    execute_query,
    generate_answer,
    generate_sql,
    inject_user_id,
    run_query_pipeline,
    validate_sql,
)

# ── In-memory rate limiter: 10 requests per 60 seconds per user_id ──────────
_rate_store: dict = defaultdict(deque)
_RATE_LIMIT = 10
_RATE_WINDOW = 60  # seconds


def _is_rate_limited(user_id: int) -> bool:
    """Returns True if the user has exceeded the rate limit."""
    now = time.time()
    window = _rate_store[user_id]
    # Evict timestamps outside the rolling window
    while window and window[0] < now - _RATE_WINDOW:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        return True
    window.append(now)
    return False


@ai_bp.route('/query', methods=['POST'])
@login_required
def query():
    # Rate limit check
    if _is_rate_limited(current_user.id):
        return jsonify({
            'status': 'error',
            'message': f'Rate limit exceeded. Maximum {_RATE_LIMIT} queries per {_RATE_WINDOW} seconds.',
        }), 429

    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()

    if not question:
        return jsonify({'status': 'error', 'message': 'question is required'}), 400
    if len(question) > 500:
        return jsonify({'status': 'error', 'message': 'question must be 500 characters or fewer'}), 400

    try:
        # Intent pre-check + (for SQL intent) the unchanged NL→SQL→answer pipeline
        response = run_query_pipeline(question, current_user.id)

        if response.get('status') == 'error':
            return jsonify(response), 400

        # Expose the generated SQL only in debug mode
        if not current_app.debug:
            response.pop('sql', None)

        return jsonify(response)

    except Exception as e:
        current_app.logger.error('AI query pipeline error: %s', e, exc_info=True)
        return jsonify({
            'status': 'error',
            'message': 'Failed to process query. Please try again.',
        }), 500
