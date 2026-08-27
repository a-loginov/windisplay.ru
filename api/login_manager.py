import os
from flask_bcrypt import Bcrypt
from flask import Flask, render_template
from flask_login import login_manager, login_required,  