from app import app

import db_manager
from api.login_manager import *
from api.admin import *
from api.ai_mod import *
from api.ai_chat import *
from api.tv import *
from api.screens import *
from api.media import *
from api.org import *
from api.webauthn_mod import *
from api.qr_login import *


if __name__ == "__main__":
    app.run(debug=True, port=9019, host="0.0.0.0")