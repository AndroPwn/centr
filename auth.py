import time
import threading
from functools import wraps
from flask import request, session, jsonify
from config import NO_AUTH
from database import get_passcode_hash

_login_attempts = {}
_login_attempts_lock = threading.Lock()
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 30

def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

def is_locked_out(ip):
    with _login_attempts_lock:
        fails, locked_until = _login_attempts.get(ip, (0, 0))
        return time.time() < locked_until

def record_login_result(ip, success):
    with _login_attempts_lock:
        fails, locked_until = _login_attempts.get(ip, (0, 0))
        if success:
            _login_attempts.pop(ip, None)
            return
        fails += 1
        if fails >= LOGIN_MAX_ATTEMPTS:
            locked_until = time.time() + LOGIN_LOCKOUT_SECONDS
            fails = 0
        _login_attempts[ip] = (fails, locked_until)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authed"):
            return jsonify({"ok": False, "error": "not authenticated"}), 401
        return view(*args, **kwargs)
    return wrapped

def ensure_passcode():
    if NO_AUTH:
        print("\n" + "=" * 50)
        print("  centr_NO_AUTH is set — passcode gate is DISABLED.")
        print("  Anyone who can reach this device's IP on the hotspot has")
        print("  full read/write access, no login required.")
        print("=" * 50)
        return
    if get_passcode_hash() is not None:
        return
    print("\n" + "=" * 50)
    print("  FIRST RUN: open the dashboard and choose your own passcode.")
    print("  Whoever sets it first becomes this device's owner. Write it")
    print("  down somewhere — it can't be recovered, only reset by wiping")
    print("  the local database.")
    print("=" * 50)
