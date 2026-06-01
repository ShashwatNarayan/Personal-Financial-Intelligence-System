from flask import render_template, redirect, url_for
from flask_login import login_required, current_user

from app.main import main_bp


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('landing.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    # CLAUDE CODE: Switched to newDashboard.html — all data is fetched client-side via JS API calls
    return render_template('dashboard/newDashboard.html')


@main_bp.route('/upload')
@login_required
def upload():
    return render_template('dashboard/upload.html')
