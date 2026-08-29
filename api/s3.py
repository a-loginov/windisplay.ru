import os

import boto3
from botocore.exceptions import ClientError
from flask import jsonify

from app import app


# --- Настройки S3 (Timeweb Cloud) ---
S3_URL = os.environ["S3_URL"]
S3_ACCESS_KEY = os.environ["S3_Access_Key"]
S3_SECRET_ACCESS_KEY = os.environ["S3_Secret_Access_Key"]
NAME_BAGET = os.environ["NAME_BAGET"]
REGUION = os.environ["REGUION"]

# Файлы кладутся в бакет под префиксом media/ — тем же
# unguessable-именем (uuid.ext), что и раньше в локальной папке.
S3_PREFIX = "media"


# Клиент S3 Service / Timeweb Cloud #
s3_client = boto3.client(
    "s3",
    endpoint_url=S3_URL,
    region_name=REGUION,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_ACCESS_KEY,
)


def s3_key(filename):
    return f"{S3_PREFIX}/{filename}"


def s3_upload(data, key, content_type=None):
    params = {"Bucket": NAME_BAGET, "Key": key, "Body": data}
    if content_type:
        params["ContentType"] = content_type
    s3_client.put_object(**params)


def s3_download(key):
    try:
        resp = s3_client.get_object(Bucket=NAME_BAGET, Key=key)
        return resp["Body"].read()
    except ClientError:
        return None


def s3_delete(key):
    try:
        s3_client.delete_object(Bucket=NAME_BAGET, Key=key)
    except ClientError:
        pass


def s3_exists(key):
    try:
        s3_client.head_object(Bucket=NAME_BAGET, Key=key)
        return True
    except ClientError:
        return False


# --- Проверка подключения к S3 ---
@app.route("/api/connect/s3", methods=["GET", "POST"])
def s3_connect_status():
    status = {
        "ok": True,
        "bucket": NAME_BAGET,
        "region": REGUION,
        "endpoint": S3_URL,
        "prefix": S3_PREFIX,
    }
    try:
        s3_client.head_bucket(Bucket=NAME_BAGET)
    except ClientError as exc:
        status.update({"ok": False, "error": str(exc)})
    return jsonify(status)


__all__ = ["s3_key", "s3_upload", "s3_download", "s3_delete", "s3_exists"]