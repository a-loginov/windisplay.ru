import config
from datetime import timedelta

from flask import Flask
from flask_login import LoginManager


app = Flask(__name__)
app.config.update(SECRET_KEY=config.SECRET_KEY)
app.permanent_session_lifetime = timedelta(days=365)

login_manager = LoginManager()
login_manager.init_app(app)