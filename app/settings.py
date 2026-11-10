import os
import secrets
import time
from pathlib import Path


DATA_DIR = Path(os.getenv("OPSFLOW_DATA_DIR", ".local")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "documents"
UPLOAD_DIR.mkdir(exist_ok=True)
COOKIE_SECURE = os.getenv("OPSFLOW_COOKIE_SECURE", "false").lower() == "true"
SESSION_SECONDS = 8 * 60 * 60
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def signing_key() -> str:
    configured = os.getenv("OPSFLOW_JWT_SECRET")
    if configured:
        if len(configured) < 32:
            raise RuntimeError("OPSFLOW_JWT_SECRET must contain at least 32 characters")
        return configured
    key_path = DATA_DIR / "jwt.key"
    try:
        with key_path.open("x", encoding="ascii") as key_file:
            key_file.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    # Another worker may have just created the file and still be writing it.
    for _attempt in range(20):
        value = key_path.read_text(encoding="ascii").strip()
        if len(value) >= 32:
            return value
        time.sleep(0.05)
    raise RuntimeError("The local signing key is incomplete")


JWT_SECRET = signing_key()
