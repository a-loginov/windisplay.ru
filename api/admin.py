import csv
import io
import functools
from datetime import date, timedelta
import config
from app import app
from flask import render_template, request, redirect, url_for, session, Response
from flask_login import login_required, current_user
from db_manager import db, User


def admin_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_panel"))
        return view(*args, **kwargs)

    return wrapper


def registrations_by_day(users, days=14):
    today = date.today()
    counts = {today - timedelta(days=i): 0 for i in range(days)}
    for user in users:
        day = user.created_at.date()
        if day in counts:
            counts[day] += 1

    ordered = [{"date": d, "count": counts[d]} for d in sorted(counts)]
    peak = max((row["count"] for row in ordered), default=0)
    for row in ordered:
        row["pct"] = round((row["count"] / peak) * 100) if peak else 4
    return ordered, peak


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin_panel():
    if not session.get("is_admin"):
        if request.method == "POST":
            if request.form.get("master_password") == config.ADMIN_MASTER_PASSWORD:
                session["is_admin"] = True
                return redirect(url_for("admin_panel"))
            return render_template("admin/gate.html", error="Неверный пароль")
        return render_template("admin/gate.html")

    users = User.query.order_by(User.created_at.desc()).all()
    today_count = sum(1 for u in users if u.created_at.date() == date.today())
    unique_companies = len({u.company for u in users})
    activity, activity_peak = registrations_by_day(users)

    return render_template(
        "admin/index.html",
        users=users,
        today_count=today_count,
        unique_companies=unique_companies,
        activity=activity,
        activity_peak=activity_peak,
    )


@app.route("/admin/exit")
@login_required
def admin_exit():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return redirect(url_for("admin_panel", error="self_delete"))

    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()

    return redirect(url_for("admin_panel", deleted="1"))


@app.route("/admin/users/export.csv")
@login_required
@admin_required
def admin_export_users():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "ФИО", "Компания", "Логин", "Дата регистрации"])
    for user in User.query.order_by(User.created_at.desc()).all():
        writer.writerow([
            user.id,
            user.full_name,
            user.company,
            user.username,
            user.created_at.strftime("%Y-%m-%d %H:%M"),
        ])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )
