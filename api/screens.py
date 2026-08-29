import json

from flask import jsonify, render_template, request, url_for
from flask_login import login_required, current_user

from app import app
from db_manager import db, Device, MediaAsset, PlaylistItem, now, new_id, make_device_token
from api.tv import ONLINE_TIMEOUT_SECONDS


def _state(device):
    if device.is_virtual:
        return "virtual"
    if not device.paired:
        return "pending"
    if device.last_seen_at and (now() - device.last_seen_at).total_seconds() < ONLINE_TIMEOUT_SECONDS:
        return "online"
    return "offline"


def _serialize(device):
    count = PlaylistItem.query.filter_by(device_id=device.id).count()
    return {
        "screenId": device.id,
        "name": device.name,
        "location": device.location,
        "virtual": bool(device.is_virtual),
        "state": _state(device),
        "createdAt": device.created_at.isoformat() + "Z" if device.created_at else None,
        "pairedAt": device.paired_at.isoformat() + "Z" if device.paired_at else None,
        "lastSeenAt": device.last_seen_at.isoformat() + "Z" if device.last_seen_at else None,
        "itemCount": count,
    }


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
    mode = (data.get("mode") or "").strip()

    if not name or not location:
        return jsonify({"error": "fields_required"}), 400

    if mode == "virtual":
        candidate = Device(
            id=new_id(),
            owner_id=current_user.id,
            name=name,
            location=location,
            is_virtual=True,
            paired_at=now(),
            created_at=now(),
        )
        db.session.add(candidate)
        db.session.commit()
        payload = _serialize(candidate)
        payload["paired"] = True
        return jsonify(payload), 201

    if not code:
        return jsonify({"error": "code_required", "message": "Введите код с экрана устройства"}), 400

    candidate = Device.query.filter_by(pair_code=code).first()
    if candidate is None or not candidate.code_valid:
        return jsonify({"error": "code_invalid", "message": "Код неверный или истёк"}), 409
    if candidate.paired:
        return jsonify({"error": "code_used", "message": "Это устройство уже привязано к аккаунту"}), 409

    candidate.name = name
    candidate.location = location
    candidate.owner_id = current_user.id
    candidate.token = make_device_token()
    candidate.paired_at = now()
    candidate.pair_code = None
    candidate.code_expires_at = None
    db.session.add(candidate)
    db.session.commit()

    payload = _serialize(candidate)
    payload["paired"] = True
    return jsonify(payload), 201



@app.route("/api/screens/<screen_id>", methods=["PATCH"])
@login_required
def screens_update(screen_id):
    device = db.session.get(Device, screen_id)
    if device is None or device.owner_id != current_user.id:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip()
    if not name or not location:
        return jsonify({"error": "fields_required"}), 400

    device.name = name
    device.location = location
    db.session.commit()
    return jsonify(_serialize(device))


@app.route("/screen/<screen_id>")
@login_required
def screen_view_page(screen_id):
    device = db.session.get(Device, screen_id)
    if device is None or device.owner_id != current_user.id or not device.is_virtual:
        return jsonify({"error": "not_found"}), 404
    return render_template(
        "virtual_screen.html",
        screen_id=device.id,
        screen_name=device.name,
        screen_location=device.location,
    )


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


@app.route("/api/screens/<screen_id>/playlist", methods=["GET"])
@login_required
def screens_playlist_get(screen_id):
    device = db.session.get(Device, screen_id)
    if device is None or device.owner_id != current_user.id:
        return jsonify({"error": "not_found"}), 404

    rows = (
        PlaylistItem.query
        .filter_by(device_id=device.id)
        .order_by(PlaylistItem.position)
        .all()
    )
    items = []
    for row in rows:
        media = db.session.get(MediaAsset, row.media_id)
        if media is None:
            continue
        items.append({
            "mediaId": media.id,
            "name": media.name,
            "kind": media.kind,
            "duration": row.duration,
            "src": url_for("media_stream", filename=media.filename, _external=True) if media.filename else None,
        })
    return jsonify({"items": items})


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