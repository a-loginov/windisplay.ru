import base64
import json
import os

from flask import jsonify, request, session, Response
from flask_login import login_required, current_user, login_user

from webauthn import (
    generate_registration_options,
    generate_authentication_options,
    verify_registration_response,
    verify_authentication_response,
    options_to_json,
    base64url_to_bytes,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)

from app import app
from db_manager import db, User, WebAuthnCredential, now


RP_NAME = "Winter.дисплей"


def _rp_id():
    configured = os.environ.get("WEBAUTHN_RP_ID")
    if configured:
        return configured
    return request.host.split(":")[0]


def _origin():
    configured = os.environ.get("WEBAUTHN_RP_ORIGIN")
    if configured:
        return configured
    return request.host_url.rstrip("/")


# ------------------------------ Регистрация устройства (из настроек) ------------------------------ #

@app.route("/api/webauthn/register/options", methods=["POST"])
@login_required
def webauthn_register_options():
    existing = WebAuthnCredential.query.filter_by(user_id=current_user.id).all()
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.username,
        user_display_name=current_user.full_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    session["webauthn_reg_challenge"] = base64.b64encode(options.challenge).decode()
    return Response(options_to_json(options), mimetype="application/json")


@app.route("/api/webauthn/register/verify", methods=["POST"])
@login_required
def webauthn_register_verify():
    challenge_b64 = session.pop("webauthn_reg_challenge", None)
    if not challenge_b64:
        return jsonify({"error": "no_challenge", "message": "Сессия регистрации истекла, попробуйте снова"}), 400

    body = request.get_data(as_text=True)
    try:
        verification = verify_registration_response(
            credential=body,
            expected_challenge=base64.b64decode(challenge_b64),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            require_user_verification=True,
        )
    except Exception:
        return jsonify({"error": "verify_failed", "message": "Не удалось подтвердить устройство"}), 400

    device_name = (request.args.get("device_name") or "").strip() or "Новое устройство"
    cred = WebAuthnCredential(
        user_id=current_user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_name=device_name[:120],
    )
    db.session.add(cred)
    db.session.commit()
    return jsonify({"ok": True, "id": cred.id, "deviceName": cred.device_name})


@app.route("/api/webauthn/credentials")
@login_required
def webauthn_list_credentials():
    creds = (
        WebAuthnCredential.query.filter_by(user_id=current_user.id)
        .order_by(WebAuthnCredential.created_at.desc())
        .all()
    )
    return jsonify({
        "items": [
            {
                "id": c.id,
                "deviceName": c.device_name,
                "createdAt": c.created_at.isoformat() + "Z",
                "lastUsedAt": c.last_used_at.isoformat() + "Z" if c.last_used_at else None,
            }
            for c in creds
        ]
    })


@app.route("/api/webauthn/credentials/<int:cred_id>", methods=["DELETE"])
@login_required
def webauthn_delete_credential(cred_id):
    cred = WebAuthnCredential.query.filter_by(id=cred_id, user_id=current_user.id).first()
    if not cred:
        return jsonify({"error": "not_found"}), 404
    db.session.delete(cred)
    db.session.commit()
    return jsonify({"ok": True})


# ------------------------------ Вход по Face ID / Touch ID (login.html) ------------------------------ #

@app.route("/api/webauthn/login/options", methods=["POST"])
def webauthn_login_options():
    options = generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    session["webauthn_auth_challenge"] = base64.b64encode(options.challenge).decode()
    return Response(options_to_json(options), mimetype="application/json")


@app.route("/api/webauthn/login/verify", methods=["POST"])
def webauthn_login_verify():
    challenge_b64 = session.pop("webauthn_auth_challenge", None)
    if not challenge_b64:
        return jsonify({"error": "no_challenge", "message": "Сессия входа истекла, попробуйте снова"}), 400

    body = request.get_data(as_text=True)
    try:
        parsed = json.loads(body)
        cred_id_bytes = base64url_to_bytes(parsed.get("rawId", ""))
    except Exception:
        return jsonify({"error": "bad_request"}), 400

    cred = WebAuthnCredential.query.filter_by(credential_id=cred_id_bytes).first()
    if not cred:
        return jsonify({"error": "unknown_credential", "message": "Это устройство не зарегистрировано ни в одном аккаунте"}), 400

    try:
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=base64.b64decode(challenge_b64),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception:
        return jsonify({"error": "verify_failed", "message": "Не удалось подтвердить вход"}), 400

    cred.sign_count = verification.new_sign_count
    cred.last_used_at = now()
    db.session.commit()

    user = User.query.get(cred.user_id)
    if not user:
        return jsonify({"error": "no_user"}), 400

    login_user(user, remember=True)
    return jsonify({"ok": True, "redirect": "/home"})
