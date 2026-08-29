from flask import jsonify, request, url_for
from flask_login import login_required, current_user

from main import app
from db_manager import db, MediaAsset, PlaylistItem, new_id, now
from storage import save_file, delete_file


def _serialize(media):
    return {
        "id": media.id,
        "name": media.name,
        "kind": media.kind,
        "mime": media.mime,
        "size": media.size,
        "url": url_for("media_stream", filename=media.filename, _external=True) if media.filename else None,
        "uploadedAt": media.uploaded_at.isoformat() + "Z" if media.uploaded_at else None,
    }


@app.route("/api/media", methods=["GET"])
@login_required
def media_list():
    rows = MediaAsset.query.filter_by(owner_id=current_user.id).order_by(MediaAsset.uploaded_at.desc()).all()
    return jsonify({"items": [_serialize(m) for m in rows]})


@app.route("/api/media", methods=["POST"])
@login_required
def media_upload():
    files = request.files.getlist("file")
    if not files:
        return jsonify({"error": "no_file"}), 400

    created = []
    for f in files:
        if not f or f.filename == "":
            continue
        try:
            filename, kind, size = save_file(f.stream, f.filename)
        except ValueError as exc:
            return jsonify({"error": str(exc), "message": f"Не поддержан тип файла: {f.filename}"}), 400

        media = MediaAsset(
            id=new_id(),
            owner_id=current_user.id,
            name=f.filename,
            kind=kind,
            mime=f.mimetype,
            size=size,
            filename=filename,
            uploaded_at=now(),
        )
        db.session.add(media)
        created.append(media)

    db.session.commit()
    return jsonify({"items": [_serialize(m) for m in created]}), 201


@app.route("/api/media/<media_id>", methods=["DELETE"])
@login_required
def media_delete(media_id):
    media = db.session.get(MediaAsset, media_id)
    if media is None or media.owner_id != current_user.id:
        return jsonify({"error": "not_found"}), 404

    PlaylistItem.query.filter_by(media_id=media.id).delete()
    delete_file(media.filename)
    db.session.delete(media)
    db.session.commit()
    return jsonify({"ok": True})