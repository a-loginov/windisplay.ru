import csv
import io
import functools
from datetime import date, datetime, timedelta
import config
import requests
from app import app
from flask import render_template, request, redirect, url_for, session, Response
from flask_login import login_required, current_user
from db_manager import db, User, Device, MediaAsset, DailySummary, get_setting, set_setting, get_bool_setting


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


def generate_daily_summary(force=False):
    today = date.today()
    existing = DailySummary.query.filter_by(day=today).first()
    if existing and not force:
        return existing
    if existing and force:
        db.session.delete(existing)
        db.session.commit()

    start = datetime.combine(today, datetime.min.time())
    new_users = User.query.filter(User.is_test.is_(False), User.created_at >= start).all()
    new_devices = Device.query.filter(Device.created_at >= start).count()
    new_media = MediaAsset.query.filter(MediaAsset.uploaded_at >= start).count()

    prompt = (
        "Ты — Комета, AI-ассистент проекта Winter.дисплей. Составь короткую (3-4 предложения) "
        "деловую сводку дня для администратора на русском языке, простым текстом без markdown. Факты:\n"
        f"- Новых регистраций: {len(new_users)}\n"
        f"- Новых компаний: {len({u.company for u in new_users})}\n"
        f"- Новых экранов: {new_devices}\n"
        f"- Новых медиафайлов: {new_media}\n"
    )

    try:
        response = requests.post(
            f"{config.OPENAI_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "Qwen 3.5 Flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6,
                "max_tokens": 300,
                "stream": False,
            },
            timeout=20,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        text = (
            f"Сегодня: {len(new_users)} новых регистраций, {new_devices} новых экранов, "
            f"{new_media} новых медиафайлов. (AI-комментарий сейчас недоступен)"
        )

    summary = DailySummary(day=today, text=text)
    db.session.add(summary)
    db.session.commit()
    return summary


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
    real_users = [u for u in users if not u.is_test]
    today_count = sum(1 for u in real_users if u.created_at.date() == date.today())
    unique_companies = len({u.company for u in real_users})
    activity, activity_peak = registrations_by_day(real_users)

    daily_summary_enabled = get_bool_setting("daily_summary_enabled", True)
    daily_summary_time = get_setting("daily_summary_time", "20:00")
    summary = None
    summary_ready = False
    if daily_summary_enabled:
        summary_ready = datetime.now().strftime("%H:%M") >= daily_summary_time
        if summary_ready:
            summary = generate_daily_summary()

    return render_template(
        "admin/index.html",
        users=users,
        real_users_count=len(real_users),
        today_count=today_count,
        unique_companies=unique_companies,
        activity=activity,
        activity_peak=activity_peak,
        daily_summary_enabled=daily_summary_enabled,
        daily_summary_time=daily_summary_time,
        summary=summary,
        summary_ready=summary_ready,
    )


@app.route("/admin/summary/regenerate", methods=["POST"])
@login_required
@admin_required
def admin_regenerate_summary():
    generate_daily_summary(force=True)
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    if request.method == "POST":
        set_setting("testing_mode", "1" if request.form.get("testing_mode") else "0")
        set_setting("daily_summary_enabled", "1" if request.form.get("daily_summary_enabled") else "0")
        daily_summary_time = (request.form.get("daily_summary_time") or "20:00").strip() or "20:00"
        set_setting("daily_summary_time", daily_summary_time)
        return redirect(url_for("admin_settings", saved="1"))

    return render_template(
        "admin/settings_project.html",
        testing_mode=get_bool_setting("testing_mode", False),
        daily_summary_enabled=get_bool_setting("daily_summary_enabled", True),
        daily_summary_time=get_setting("daily_summary_time", "20:00"),
        test_users_count=User.query.filter_by(is_test=True).count(),
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
