import config
from flask import Flask, render_template, url_for, session
from datetime import timedelta


app = Flask(__name__)
app.config.update(SECRET_KEY=config.SECRET_KEY)
app.permanent_session_lifetime = timedelta(days=365)


from api.login_manager import *
#from api.tv import tv








if __name__ == "__main__":
    app.run(debug=True, port=9019, host="0.0.0.0")
