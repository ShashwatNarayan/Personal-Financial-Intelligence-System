from datetime import datetime

import requests
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message

from app import db, limiter, mail
from app.auth import auth_bp
from app.auth.forms import (
    LoginForm,
    RegisterForm,
    ResetPasswordForm,
    ResetPasswordRequestForm,
)
from app.models import UploadLog, User

RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'
RECAPTCHA_MIN_SCORE = 0.5


def _verify_recaptcha(token=None):
    return True  # disabled until RECAPTCHA keys are configured
    # --- Re-enable by deleting the early return above; original body below. ---
    # token = request.form.get('g-recaptcha-response', '')
    # secret = current_app.config.get('RECAPTCHA_SECRET_KEY')
    # try:
    #     resp = requests.post(
    #         RECAPTCHA_VERIFY_URL,
    #         data={
    #             'secret': secret,
    #             'response': token,
    #             'remoteip': request.remote_addr,
    #         },
    #         timeout=10,
    #     )
    #     result = resp.json()
    # except Exception:
    #     current_app.logger.exception('reCAPTCHA verification request failed')
    #     return False
    #
    # return result.get('success', False) and result.get('score', 0) >= RECAPTCHA_MIN_SCORE


def _send_password_reset_email(user):
    token = user.get_reset_token()
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    msg = Message('ArthaLens — Reset Your Password', recipients=[user.email])
    msg.body = (
        f'Hi,\n\n'
        f'To reset your ArthaLens password, click the link below:\n'
        f'{reset_url}\n\n'
        f'This link expires in 30 minutes. If you did not request a password '
        f'reset, you can safely ignore this email — your password will not change.\n'
    )
    mail.send(msg)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegisterForm()

    if request.method == 'POST' and not _verify_recaptcha():
        flash('Verification failed. Please try again.', 'danger')
        return render_template('auth/register.html', form=form)

    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html', form=form)

        user = User(email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        login_user(user)  # auto-login after registration
        return redirect(url_for('main.upload'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()

    if request.method == 'POST' and not _verify_recaptcha():
        flash('Verification failed. Please try again.', 'danger')
        return render_template('auth/login.html', form=form)

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if not user or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html', form=form)

        login_user(user)
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        # Existing users (with prior uploads) land on the dashboard; users who
        # have never uploaded keep going to the upload page.
        has_uploads = UploadLog.query.filter_by(user_id=user.id).first() is not None
        return redirect(url_for('main.dashboard' if has_uploads else 'main.upload'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/reset_password', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            try:
                _send_password_reset_email(user)
            except Exception:
                current_app.logger.exception('Failed to send password reset email')
        # Always show the same message to avoid leaking which emails are registered.
        flash(
            'If an account exists for that email, a password reset link has been sent.',
            'info',
        )
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_request.html', form=form)


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    user = User.verify_reset_token(token)
    if user is None:
        flash('That password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.reset_password_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been updated. Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
