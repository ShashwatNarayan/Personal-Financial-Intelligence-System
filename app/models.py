from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    entity_memory = db.relationship('EntityMemory', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    corrections = db.relationship('Correction', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    uploads = db.relationship('UploadLog', backref='user', cascade='all, delete-orphan', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class EntityMemory(db.Model):
    __tablename__ = 'entity_memory'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    entity_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    confidence = db.Column(db.Float, default=1.0)
    correction_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'entity_name', name='uq_entity_memory_user_entity'),
    )

    def __repr__(self):
        return f'<EntityMemory {self.entity_name} → {self.category}>'


class UploadLog(db.Model):
    __tablename__ = 'uploads_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255))
    bank_detected = db.Column(db.String(50))
    row_count = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='upload', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<UploadLog {self.filename} ({self.row_count} rows)>'


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    upload_id = db.Column(db.Integer, db.ForeignKey('uploads_log.id', ondelete='CASCADE'), nullable=False)
    txn_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text)
    entity_name = db.Column(db.String(255))
    amount = db.Column(db.Numeric(12, 2))
    transaction_type = db.Column(db.String(10))
    category = db.Column(db.String(100))
    entity_type = db.Column(db.String(50))
    confidence_level = db.Column(db.String(20))
    is_reimbursed = db.Column(db.Boolean, default=False)

    corrections = db.relationship('Correction', backref='transaction', cascade='all, delete-orphan', lazy='dynamic')

    __table_args__ = (
        db.Index('ix_transactions_user_date', 'user_id', 'txn_date'),
    )

    def __repr__(self):
        return f'<Transaction {self.txn_date} {self.entity_name} ₹{self.amount}>'


class Correction(db.Model):
    __tablename__ = 'corrections'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False)
    entity_name = db.Column(db.String(255))
    old_category = db.Column(db.String(100))
    new_category = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Correction {self.entity_name}: {self.old_category} → {self.new_category}>'
