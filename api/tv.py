import os
import mimetypes
from datetime import timedelta
from io import BytesIO

from flask import jsonify, request, send_file, url_for

from app import app
from db_manager import db, Device, PlaylistItem, MediaAsset, new_id, make_pair_code, make_device_token, now
from api.s3 import s3_key, s3_download


CODE_TTL_MINUTES = 5
ONLINE_TIMEOUT_SECONDS = 90


def device_from_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):].strip()
    if not token:
        return None
    return Device.query.filter_by(token=token).first()


# ------------------------------ Pairing ------------------------------ #


@app.route("/api/device/register", methods=["POST"])
def device_register():
    """Устройство просит код спаривания. Возвращает deviceId + code + expiresAt."""
    data = request.get_json(silent=True) or {}
    device_id = data.get("deviceId") or None

    if device_id:
        device = db.session.get(Device, device_id)
        if device is None:
            return jsonify({"error": "device_not_found"}), 404
    else:
        device = Device(id=new_id(), created_at=now())

    device.pair_code = make_pair_code()
    device.code_expires_at = now() + timedelta(minutes=CODE_TTL_MINUTES)
    db.session.add(device)
    db.session.commit()

    return jsonify({
        "deviceId": device.id,
        "code": device.pair_code,
        "expiresAt": device.code_expires_at.isoformat() + "Z",
    })


@app.route("/api/device/pair/status")
def device_pair_status():
    device_id = request.args.get("deviceId", "")
    device = db.session.get(Device, device_id) if device_id else None
    if device is None:
        return jsonify({"paired": False}), 404

    if device.paired:
        return jsonify({
            "paired": True,
            "token": device.token,
            "deviceName": device.name,
        })
    return jsonify({"paired": False})


# ------------------------------ Player ------------------------------ #


@app.route("/api/device/playlist")
def device_playlist():
    device = device_from_token()
    if device is None:
        return jsonify({"error": "unauthorized"}), 401

    items = (
        PlaylistItem.query
        .filter_by(device_id=device.id)
        .order_by(PlaylistItem.position)
        .all()
    )

    result = []
    for item in items:
        media = db.session.get(MediaAsset, item.media_id)
        if media is None or not media.filename:
            continue
        result.append({
            "id": media.id,
            "type": media.kind,
            "duration": item.duration or 8,
            "url": url_for("media_stream", filename=media.filename, _external=True),
        })

    return jsonify({"items": result, "updatedAt": device.last_seen_at})


@app.route("/api/device/heartbeat", methods=["POST"])
def device_heartbeat():
    device = device_from_token()
    if device is None:
        return jsonify({"error": "unauthorized"}), 401
    device.last_seen_at = now()
    db.session.commit()
    return jsonify({"ok": True, "lastSeenAt": device.last_seen_at.isoformat() + "Z"})


# ------------------------------ Media stream ------------------------------ #
# Файлы лежат по unguessable-имени (uuid.ext): ссылка действует как «ключ».
# Это осознанное упрощение Фазы 1: плеер скачивает media без заголовка Authorization.


@app.route("/media/<path:filename>")
def media_stream(filename):
    name = os.path.basename(filename)
    data = s3_download(s3_key(name))
    if data is None:
        return jsonify({"error": "not_found"}), 404
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return send_file(BytesIO(data), mimetype=mime, conditional=True, max_age=0)