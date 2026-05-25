import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
