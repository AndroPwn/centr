import os
import secrets
from flask import Flask
from flask_cors import CORS
from config import STATIC_DIR, SESSION_KEY_PATH

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
CORS(app)

if os.path.isfile(SESSION_KEY_PATH):
    with open(SESSION_KEY_PATH, "rb") as f:
        app.secret_key = f.read()
else:
    app.secret_key = secrets.token_bytes(32)
    with open(SESSION_KEY_PATH, "wb") as f:
        f.write(app.secret_key)
    os.chmod(SESSION_KEY_PATH, 0o600)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
)
