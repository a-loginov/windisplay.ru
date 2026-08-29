import os
import uuid
from pathlib import Path

from main import app

MEDIA_DIR = Path(app.root_path) / "media"

ALLOWED_EXT = {
    "images": {"jpg", "jpeg", "png", "gif", "webp"},
    "videos": {"mp4", "webm", "mov"},
}
KIND_BY_EXT = {
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image", "webp": "image",
    "mp4": "video", "webm": "video", "mov": "video",
}


def allowed(name):
    ext = Path(name).suffix.lstrip(".").lower()
    return ext in KIND_BY_EXT, ext


def save_file(stream, original_name):
    """Сохраняет поток в media/, возвращает имя файла на диске и метаданные."""
    ok, ext = allowed(original_name)
    if not ok:
        raise ValueError("unsupported_type")

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = MEDIA_DIR / filename
    size = 0
    with open(path, "wb") as fh:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            fh.write(chunk)
            size += len(chunk)
    if size == 0:
        path.unlink(missing_ok=True)
        raise ValueError("empty_file")
    return filename, KIND_BY_EXT[ext], size


def delete_file(filename):
    if not filename:
        return
    try:
        (MEDIA_DIR / filename).unlink(missing_ok=True)
    except OSError:
        pass


def media_path(filename):
    return MEDIA_DIR / filename