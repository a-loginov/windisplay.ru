import io
from datetime import timedelta

import qrcode
from flask import jsonify, request, send_file, render_template, redirect, url_for
from flask_login import login_required, current_user, login_user

from app import app
from db_manager import db, User, QrLoginSession, make_qr_token, now


QR_TTL_SECONDS = 120


@app.route("/api/qr/start", methods=["POST"])
def qr_start():
    QrLoginSession.query.filter(QrLoginSession.expires_at < now()).delete()

    session_row = QrLoginSession(
        token=make_qr_token(),
        status="pending",
        expires_at=now() + timedelta(seconds=QR_TTL_SECONDS),
    )
    db.session.add(session_row)
    db.session.commit()

    confirm_url = f"{request.host_url.rstrip('/')}/qr/confirm?token={session_row.token}"
    return jsonify({"token": session_row.token, "confirmUrl": confirm_url, "expiresIn": QR_TTL_SECONDS})


@app.route("/api/qr/image/<token>.png")
def qr_image(token):
    session_row = QrLoginSession.query.filter_by(token=token).first()
    if not session_row or not session_row.valid:
        return jsonify({"error": "expired"}), 404

    confirm_url = f"{request.host_url.rstrip('/')}/qr/confirm?token={token}"
    img = qrcode.make(confirm_url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/qr/status/<token>")
def qr_status(token):
    session_row = QrLoginSession.query.filter_by(token=token).first()
    if not session_row or not session_row.valid:
        return jsonify({"status": "expired"})
    return jsonify({"status": session_row.status})


@app.route("/api/qr/claim/<token>", methods=["POST"])
def qr_claim(token):
    session_row = QrLoginSession.query.filter_by(token=token).first()
    if not session_row or not session_row.valid or session_row.status != "confirmed":
        return jsonify({"error": "not_ready"}), 400

    user = User.query.get(session_row.user_id) if session_row.user_id else None
    if not user:
        return jsonify({"error": "no_user"}), 400

    session_row.status = "claimed"
    db.session.commit()

    login_user(user, remember=True)
    return jsonify({"ok": True, "redirect": "/home"})


# ------------------------------ Страница подтверждения на телефоне ------------------------------ #

@app.route("/qr/confirm")
@login_required
def qr_confirm_page():
    token = request.args.get("token", "")
    session_row = QrLoginSession.query.filter_by(token=token).first()
    if not session_row or not session_row.valid:
        return render_template("qr_confirm.html", state="expired")
    if session_row.status != "pending":
        return render_template("qr_confirm.html", state="done")
    return render_template("qr_confirm.html", state="pending", token=token)


@app.route("/api/qr/confirm/<token>", methods=["POST"])
@login_required
def qr_confirm_submit(token):
    session_row = QrLoginSession.query.filter_by(token=token).first()
    if not session_row or not session_row.valid or session_row.status != "pending":
        return jsonify({"error": "not_pending"}), 400

    session_row.status = "confirmed"
    session_row.user_id = current_user.id
    db.session.commit()
    return jsonify({"ok": True})
