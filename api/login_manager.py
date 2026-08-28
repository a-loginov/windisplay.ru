import os
import secrets
import requests
from flask_bcrypt import Bcrypt
from main import app
from flask import Flask, render_template, jsonify
from flask_login import login_required, current_user




# ------------------------------ Frontend ------------------------------ #
@app.route("/")
def login():
    return render_template("login.html")


@app.route("/home")
@login_required
def home():
    return render_template("home.html")

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/account')
@login_required
def account():
    return render_template('account.html')


@app.route('/create_profile')
def create_teacher_profile():
    return render_template('create_profile.html')

# ------------------------------ Backend ------------------------------ #


# Тестововый режим #
PEOPLE_INVATIE_PASSWORD="РОУТЕРСКИЙ"



