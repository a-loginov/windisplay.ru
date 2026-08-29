import os
import secrets
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import deferred
from sqlalchemy import UUID, text
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from main import app, config, login_manager


# Долгие числа/буквы без «нечитаемых» символов (0/O, 1/I/L)
PAIR_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def new_id():
    return uuid.uuid4().hex


def make_pair_code(length=6):
    return "".join(secrets.choice(PAIR_CODE_ALPHABET) for _ in range(length))


def make_device_token():
    return secrets.token_urlsafe(32)


def now():
    return datetime.utcnow()



# Инцилизация БД для работы #
POSTGRESQL_HOST=os.environ["POSTGRESQL_HOST"]
POSTGRESQL_PORT=os.environ["POSTGRESQL_PORT"]
POSTGRESQL_USER=os.environ["POSTGRESQL_USER"]
POSTGRESQL_PASSWORD=os.environ["POSTGRESQL_PASSWORD"]
POSTGRESQL_DBNAME=os.environ["POSTGRESQL_DBNAME"]


app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql+psycopg2://{POSTGRESQL_USER}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}:{POSTGRESQL_PORT}/{POSTGRESQL_DBNAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
}
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    company = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class MediaAsset(db.Model):
    __tablename__ = "media_assets"
    id = db.Column(db.String(36), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(16), nullable=False)  # image | video | file
    mime = db.Column(db.String(80))
    size = db.Column(db.Integer, default=0)
    # имя файла на диске, например "ab12cd34ef.mp4"; unguessable = uid
    filename = db.Column(db.String(128))
    uploaded_at = db.Column(db.DateTime, default=now, nullable=False)


class Device(db.Model):
    __tablename__ = "devices"
    id = db.Column(db.String(36), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(120), default="")
    location = db.Column(db.String(120), default="")
    token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    pair_code = db.Column(db.String(8), nullable=True, index=True)
    code_expires_at = db.Column(db.DateTime, nullable=True)
    paired_at = db.Column(db.DateTime, nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

    @property
    def paired(self):
        return self.token is not None and self.owner_id is not None

    @property
    def code_valid(self):
        return self.pair_code is not None and self.code_expires_at is not None and self.code_expires_at > now()


class PlaylistItem(db.Model):
    __tablename__ = "playlist_items"
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(36), db.ForeignKey("devices.id"), nullable=False, index=True)
    media_id = db.Column(db.String(36), db.ForeignKey("media_assets.id"), nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    duration = db.Column(db.Integer, default=8, nullable=False)



