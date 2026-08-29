import json

from flask import jsonify, request
from flask_login import login_required, current_user

from main import app
from db_manager import db, Device, MediaAsset, PlaylistItem, now, make_device_token, new_id
from api.tv import ONLINE_TIMEOUT_SECONDS


def _state(device):
    if not device.paired:
        return "pending"
    if device.last_seen_at and (now() - device.last_seen_at).total_seconds() < ONLINE_TIMEOUT_SECONDS:
        return "online"
    return "offline"


def _serialize(device):
    count = PlaylistItem.query.filter_by(device_id=device.id).count()
    payload = {
        "screenId": device.id,
        "name": device.name,
        "location": device.location,
        "state": _state(device),
        "createdAt": device.created_at.isoformat() + "Z" if device.created_at else None,
        "pairedAt": device.paired_at.isoformat() + "Z" if device.paired_at else None,
        "lastSeenAt": device.last_seen_at.isoformat() + "Z" if device.last_seen_at else None,
        "itemCount": count,
    }
    if not device.paired and device.pair_code:
        payload["pairCode"] = device.pair_code
    return payload


@app.route("/api/screens")
@login_required
def screens_list():
    devices = Device.query.filter_by(owner_id=current_user.id).order_by(Device.created_at.desc()).all()
    return jsonify({"items": [_serialize(d) for d in devices]})


@app.route("/api/screens", methods=["POST"])
@login_required
def screens_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip()
    code = (data.get("code") or "").strip().upper()

    if not name or not location:
        return jsonify({"error": "fields_required"}), 400

    paired = False
    if code:
        candidate = Device.query.filter_by(pair_code=code).first()
        if candidate is None or not candidate.code_valid:
            return jsonify({"error": "code_invalid", "message": "Код неверный или истёк"}), 409
        if candidate.paired:
            return jsonify({"error": "code_used", "message": "Это устройство уже привязано к аккаунту"}), 409
        device = candidate
        device.name = name
        device.location = location
        device.owner_id = current_user.id
        device.token = make_device_token()
        device.paired_at = now()
        device.pair_code = None
        device.code_expires_at = None
        paired = True
    else:
        device = Device(
            id=new_id(),
            owner_id=current_user.id,
            name=name,
            location=location,
            created_at=now(),
        )

    db.session.add(device)
    db.session.commit()

    payload = _serialize(device)
    payload["paired"] = paired
    return jsonify(payload), 201


@app.route("/api/screens/<screen_id>/pair", methods=["POST"])
@login_required
def screens_pair(screen_id):
    device = db.session.get(Device, screen_id)
    if device is None or device.owner_id != current_user.id:
        return jsonify({"error": "not_found"}), 404
    if device.paired:
        return jsonify(_serialize(device))

    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    candidate = Device.query.filter_by(pair_code=code).first()
    if candidate is None or not candidate.code_valid:
        return jsonify({"error": "code_invalid", "message": "Код неверный или истёк"}), 409
    if candidate.paired:
        return jsonify({"error": "code_used", "message": "Это устройство уже привязано к аккаунту"}), 409

    # переносим код-устройство в «окно» экрана
    device.owner_id = current_user.id
    device.token = make_device_token()
    device.paired_at = now()
    device.pair_code = None
    device.code_expires_at = None
    candidate.owner_id = None
    candidate.token = None
    candidate.pair_code = None
    candidate.code_expires_at = None
    db.session.commit()

    return jsonify(_serialize(device))


@app.route("/api/screens/<screen_id>", methods=["DELETE"])
@login_required
def screens_delete(screen_id):
    device = db.session.get(Device, screen_id)
    if device is None or device.owner_id != current_user.id:
        return jsonify({"error": "not_found"}), 404

    PlaylistItem.query.filter_by(device_id=device.id).delete()
    db.session.delete(device)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/screens/<screen_id>/playlist", methods=["POST"])
@login_required
def screens_playlist(screen_id):
    device = db.session.get(Device, screen_id)
    if device is None or device.owner_id != current_user.id:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list):
        return jsonify({"error": "items_required"}), 400

    owned_media = {m.id for m in MediaAsset.query.filter_by(owner_id=current_user.id).all()}
    prepared = []
    for i, it in enumerate(items):
        media_id = str(it.get("mediaId") or "")
        if media_id not in owned_media:
            return jsonify({"error": "media_not_owned", "message": f"Медиа {media_id} не принадлежит аккаунту"}), 400
        try:
            duration = int(it.get("duration") or 8)
        except (TypeError, ValueError):
            duration = 8
        prepared.append((i, media_id, max(duration, 1)))

    PlaylistItem.query.filter_by(device_id=device.id).delete()
    for i, media_id, duration in prepared:
        db.session.add(PlaylistItem(device_id=device.id, media_id=media_id, position=i, duration=duration))
    db.session.commit()

    return jsonify({"ok": True, "count": len(prepared)})