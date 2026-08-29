import os
import secrets
import requests
from flask_bcrypt import Bcrypt
from main import app
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_login import login_required, current_user, login_user, logout_user
from db_manager import db, User, OrgInvite, get_bool_setting




# ------------------------------ Frontend ------------------------------ #
@app.route("/")
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    username = (request.form.get("login") or "").strip()
    password = request.form.get("password") or ""
    user = User.query.filter_by(username=username).first() if username else None

    if user is None or not user.check_password(password):
        return render_template("login.html", error="Неверный логин или пароль")

    login_user(user, remember=True)
    return redirect(url_for("home"))


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


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


def _find_invite(token):
    if not token:
        return None
    invite = OrgInvite.query.filter_by(token=token).first()
    return invite if invite and invite.valid else None


@app.route('/create_profile', methods=['GET', 'POST'])
def create_teacher_profile():
    invite_token = request.args.get('invite', '') if request.method == 'GET' else request.form.get('invite_token', '')
    invite = _find_invite(invite_token)

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if invite:
            company = invite.company
        else:
            invite_password = request.form.get('invite_password', '')
            if invite_password != PEOPLE_INVATIE_PASSWORD:
                return render_template('create_profile.html', error='Неверный пригласительный код', error_step='invite')
            company = request.form.get('company', '').strip()

        if not full_name or not company or not username or not password:
            return render_template(
                'create_profile.html',
                error='Заполните все поля',
                error_step='details',
                form=request.form,
                invite_password=request.form.get('invite_password', ''),
                invite=invite,
            )

        if User.query.filter_by(username=username).first():
            return render_template(
                'create_profile.html',
                error='Этот логин уже занят',
                error_step='details',
                form=request.form,
                invite_password=request.form.get('invite_password', ''),
                invite=invite,
            )

        if invite:
            role = 'member'
        else:
            role = 'owner' if User.query.filter_by(company=company).first() is None else 'member'

        user = User(
            username=username,
            full_name=full_name,
            company=company,
            role=role,
            is_test=get_bool_setting("testing_mode", False),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user, remember=True)
        return redirect(url_for('home'))

    return render_template('create_profile.html', invite=invite)

# ------------------------------ Backend ------------------------------ #


# Тестововый режим #
PEOPLE_INVATIE_PASSWORD="РОУТЕРСКИЙ"



