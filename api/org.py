from datetime import timedelta

from flask import jsonify, request
from flask_login import login_required, current_user

from app import app
from db_manager import db, User, Device, MediaAsset, OrgInvite, make_invite_token, now


ROLE_LABELS = {"owner": "Владелец", "admin": "Администратор", "member": "Участник"}
INVITE_TTL_DAYS = 14


def _role(user):
    return user.role if user.role in ROLE_LABELS else "member"


@app.route("/api/org")
@login_required
def org_info():
    org_name = (current_user.company or "").strip()
    if org_name:
        members = User.query.filter_by(company=org_name).order_by(User.created_at.asc()).all()
    else:
        members = []

    member_ids = [u.id for u in members]
    if member_ids:
        screens = db.session.query(db.func.count(Device.id)).filter(Device.owner_id.in_(member_ids)).scalar() or 0
        media = db.session.query(db.func.count(MediaAsset.id)).filter(MediaAsset.owner_id.in_(member_ids)).scalar() or 0
    else:
        screens = 0
        media = 0

    return jsonify({
        "name": org_name,
        "stats": {
            "members": len(members),
            "screens": screens,
            "media": media,
        },
        "me": {
            "id": current_user.id,
            "username": current_user.username,
            "fullName": current_user.full_name,
            "role": _role(current_user),
            "isMe": True,
        },
        "members": [
            {
                "id": u.id,
                "username": u.username,
                "fullName": u.full_name,
                "role": _role(u),
                "isMe": u.id == current_user.id,
                "joinedAt": u.created_at.isoformat() + "Z" if u.created_at else None,
            }
            for u in members
        ],
    })


@app.route("/api/org/invite", methods=["POST"])
@login_required
def org_create_invite():
    org_name = (current_user.company or "").strip()
    if not org_name:
        return jsonify({"error": "no_company", "message": "У аккаунта не указана компания"}), 400

    if _role(current_user) not in ("owner", "admin"):
        return jsonify({"error": "forbidden", "message": "Приглашать участников может только владелец или администратор"}), 403

    invite = (
        OrgInvite.query.filter_by(company=org_name)
        .order_by(OrgInvite.created_at.desc())
        .first()
    )
    if invite is None or not invite.valid:
        invite = OrgInvite(
            token=make_invite_token(),
            company=org_name,
            created_by_id=current_user.id,
            expires_at=now() + timedelta(days=INVITE_TTL_DAYS),
        )
        db.session.add(invite)
        db.session.commit()

    return jsonify({
        "token": invite.token,
        "url": f"{request.host_url.rstrip('/')}/create_profile?invite={invite.token}",
        "expiresAt": invite.expires_at.isoformat() + "Z" if invite.expires_at else None,
    })