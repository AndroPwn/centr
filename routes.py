import os
import io
import sys
import uuid
import json
import time
from flask import request, jsonify, send_from_directory, send_file, session
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import RNS

from app import app
from config import NO_AUTH, APP_NAME, ASPECT, IMAGES_DIR, FILES_DIR, MEDIA_EXT_BY_MIME, MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, MAX_FILE_BYTES, media_kind_from_mime, RETICULUM_CONFIG_DIR, APK_DIR, APK_FILENAME, EXE_FILENAME, TERMUX_APK_FILENAME
from auth import login_required, is_locked_out, record_login_result, client_ip
import network
from database import conn, db_lock, insert_message, update_message_status, get_passcode_hash, set_passcode_hash, get_max_receive_size, set_max_receive_size, get_display_name, set_display_name, DISPLAY_NAME_MAX_LEN

PUBLIC_PATHS = {"/api/auth/login", "/api/auth/status", "/api/auth/setup", "/download/bundle", "/download/apk", "/download/exe", "/download/termux"}
PUBLIC_PREFIXES = ("/icons/",)
PUBLIC_STATIC_FILES = {"/", "/index.html", "/manifest.json", "/sw.js"}

@app.before_request
def require_login():
    if NO_AUTH:
        return None
    path = request.path
    if path in PUBLIC_PATHS or path in PUBLIC_STATIC_FILES or path.startswith(PUBLIC_PREFIXES):
        return None
    if path.startswith("/api/") or path.startswith("/download/"):
        if not session.get("authed"):
            return jsonify({"ok": False, "error": "not authenticated"}), 401
    return None

@app.route("/api/auth/status", methods=["GET"])
def api_auth_status():
    return jsonify({
        "authed": True if NO_AUTH else bool(session.get("authed")),
        "needs_setup": (not NO_AUTH) and get_passcode_hash() is None,
    })

@app.route("/api/auth/setup", methods=["POST"])
def api_auth_setup():
    if NO_AUTH:
        return jsonify({"ok": False, "error": "Auth is disabled on this device"}), 400
    if get_passcode_hash() is not None:
        return jsonify({"ok": False, "error": "Passcode already set — use login instead"}), 400

    data = request.get_json(force=True) or {}
    passcode = (data.get("passcode") or "").strip()
    if len(passcode) < 4:
        return jsonify({"ok": False, "error": "Passcode must be at least 4 characters"}), 400

    set_passcode_hash(generate_password_hash(passcode))

    session.permanent = True
    session["authed"] = True
    return jsonify({"ok": True})

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    ip = client_ip()
    if is_locked_out(ip):
        return jsonify({"ok": False, "error": "Too many attempts — wait a bit and try again"}), 429

    data = request.get_json(force=True) or {}
    passcode = (data.get("passcode") or "").strip()
    pw_hash = get_passcode_hash()

    ok = bool(pw_hash) and check_password_hash(pw_hash, passcode)
    record_login_result(ip, ok)
    if not ok:
        return jsonify({"ok": False, "error": "Incorrect passcode"}), 401

    session.permanent = True
    session["authed"] = True
    return jsonify({"ok": True})

@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/change-passcode", methods=["POST"])
@login_required
def api_auth_change_passcode():
    data = request.get_json(force=True) or {}
    current = (data.get("current") or "").strip()
    new = (data.get("new") or "").strip()

    pw_hash = get_passcode_hash()
    if not pw_hash or not check_password_hash(pw_hash, current):
        return jsonify({"ok": False, "error": "Current passcode is incorrect"}), 401
    if len(new) < 4:
        return jsonify({"ok": False, "error": "New passcode must be at least 4 characters"}), 400

    set_passcode_hash(generate_password_hash(new))
    return jsonify({"ok": True})

@app.route("/")
def index_page():
    return app.send_static_file("index.html")

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({"address": network.destination.hash.hex(), "app_name": APP_NAME, "aspect": ASPECT})

@app.route("/api/announce", methods=["POST"])
def api_announce():
    network.reannounce()
    return jsonify({"ok": True})

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    with db_lock:
        row = conn.execute("SELECT value FROM settings WHERE key='relay_enabled_pending'").fetchone()
    pending = (row[0] == "1") if row else network.CURRENT_TRANSPORT_ENABLED
    return jsonify({
        "address": network.destination.hash.hex(),
        "relay_enabled_active": network.CURRENT_TRANSPORT_ENABLED,
        "relay_enabled_pending": pending,
        "restart_required": pending != network.CURRENT_TRANSPORT_ENABLED,
        "max_recv_bytes": get_max_receive_size(),
        "display_name": get_display_name(),
        "display_name_max_len": DISPLAY_NAME_MAX_LEN,
    })

@app.route("/api/settings/display_name", methods=["POST"])
def api_set_display_name():
    data = request.get_json(force=True) or {}
    name = (data.get("display_name") or "").strip()
    if len(name) > DISPLAY_NAME_MAX_LEN:
        return jsonify({"ok": False, "error": f"Display name must be {DISPLAY_NAME_MAX_LEN} characters or fewer"}), 400
    saved = set_display_name(name)
    network.reannounce()
    return jsonify({"ok": True, "display_name": saved})

@app.route("/api/settings/max_size", methods=["POST"])
def api_set_max_size():
    data = request.get_json(force=True) or {}
    try:
        size_bytes = int(data.get("max_recv_bytes"))
        set_max_receive_size(size_bytes)
        return jsonify({"ok": True})
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid size"}), 400

@app.route("/api/settings/relay", methods=["POST"])
def api_set_relay():
    data = request.get_json(force=True) or {}
    enabled = bool(data.get("enabled"))
    network.patch_config_transport_flag(RETICULUM_CONFIG_DIR, enabled)
    with db_lock:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('relay_enabled_pending', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("1" if enabled else "0",),
        )
        conn.commit()
    return jsonify({"ok": True, "restart_required": enabled != network.CURRENT_TRANSPORT_ENABLED})

@app.route("/api/peers", methods=["GET"])
def api_peers():
    with db_lock:
        rows = conn.execute(
            "SELECT hash, nickname, announced_name, last_seen FROM peers ORDER BY last_seen DESC"
        ).fetchall()
    return jsonify([
        {
            "hash": r[0],
            "nickname": r[1],
            "announced_name": r[2],
            "display_name": r[1] or r[2] or (r[0][:10] + "…"),
            "last_seen": r[3],
        }
        for r in rows
    ])

@app.route("/api/peers/<peer_hash>/nickname", methods=["POST"])
def api_set_nickname(peer_hash):
    data = request.get_json(force=True) or {}
    nickname = (data.get("nickname") or "").strip()
    with db_lock:
        conn.execute(
            "INSERT INTO peers(hash,nickname,last_seen) VALUES (?,?,COALESCE("
            "(SELECT last_seen FROM peers WHERE hash=?),0)) "
            "ON CONFLICT(hash) DO UPDATE SET nickname=excluded.nickname",
            (peer_hash, nickname, peer_hash),
        )
        conn.commit()
    return jsonify({"ok": True})

@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    with db_lock:
        peer_rows = conn.execute(
            "SELECT peer_hash, MAX(ts) FROM messages WHERE group_id IS NULL AND peer_hash IS NOT NULL "
            "GROUP BY peer_hash"
        ).fetchall()
        group_rows = conn.execute("SELECT group_id, name FROM groups").fetchall()
        nick_rows = {}
        for h, nickname, announced_name in conn.execute("SELECT hash, nickname, announced_name FROM peers"):
            nick_rows[h] = nickname or announced_name

        last_peer_msg = {}
        for ph, body, mtype, ts in conn.execute(
            "SELECT peer_hash, body, mtype, ts FROM messages WHERE group_id IS NULL ORDER BY ts DESC"
        ):
            if ph not in last_peer_msg:
                last_peer_msg[ph] = {"preview": body if mtype == "text" else f"[{mtype}]", "ts": ts}

        last_group_msg = {}
        for gid, body, mtype, ts in conn.execute(
            "SELECT group_id, body, mtype, ts FROM messages WHERE group_id IS NOT NULL ORDER BY ts DESC"
        ):
            if gid not in last_group_msg:
                last_group_msg[gid] = {"preview": body if mtype == "text" else f"[{mtype}]", "ts": ts}

    out = []
    for ph, last_ts in peer_rows:
        info = last_peer_msg.get(ph, {})
        out.append({
            "kind": "peer", "id": ph,
            "label": nick_rows.get(ph) or ph[:10],
            "preview": info.get("preview", ""),
            "ts": info.get("ts", last_ts) or 0,
        })
    for gid, name in group_rows:
        info = last_group_msg.get(gid, {})
        out.append({
            "kind": "group", "id": gid, "label": name,
            "preview": info.get("preview", ""),
            "ts": info.get("ts", 0) or 0,
        })
    out.sort(key=lambda x: x["ts"], reverse=True)
    return jsonify(out)

@app.route("/api/messages", methods=["GET"])
def api_get_messages():
    peer = request.args.get("peer")
    group = request.args.get("group")
    with db_lock:
        if group:
            rows = conn.execute(
                "SELECT id, peer_hash, direction, mtype, body, status, ts FROM messages "
                "WHERE group_id=? ORDER BY ts ASC", (group,)
            ).fetchall()
        elif peer:
            rows = conn.execute(
                "SELECT id, peer_hash, direction, mtype, body, status, ts FROM messages "
                "WHERE group_id IS NULL AND peer_hash=? ORDER BY ts ASC", (peer,)
            ).fetchall()
        else:
            return jsonify([])
    return jsonify([
        {"id": r[0], "peer_hash": r[1], "direction": r[2], "type": r[3], "body": r[4], "status": r[5], "ts": r[6]}
        for r in rows
    ])

@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json(force=True) or {}
    dest_hex = (data.get("destination") or "").strip()
    text = (data.get("message") or "").strip()
    if not dest_hex or not text:
        return jsonify({"ok": False, "error": "destination and message are required"}), 400

    mid = str(uuid.uuid4())
    ts = time.time()
    insert_message(mid, dest_hex, None, "out", "text", text, "queued", ts)

    envelope = {"mid": mid, "from": network.destination.hash.hex(), "type": "text", "body": text, "ts": ts}
    ok, err = network.try_send_envelope_to_peer(dest_hex, envelope)
    if ok:
        update_message_status(mid, "sent")
        return jsonify({"ok": True, "mid": mid})
    return jsonify({"ok": True, "mid": mid, "queued": True, "note": err}), 202

@app.route("/api/send-media", methods=["POST"])
def api_send_media():
    dest_hex = (request.form.get("destination") or "").strip()
    file = request.files.get("media")
    if not dest_hex or file is None:
        return jsonify({"ok": False, "error": "destination and media are required"}), 400

    mime = (file.mimetype or "").lower()
    kind = media_kind_from_mime(mime)
    original_name = file.filename or "unknown"

    data = file.read()

    # Determine size limit based on kind
    if kind == "video":
        max_bytes = MAX_VIDEO_BYTES
    elif kind == "image":
        max_bytes = MAX_IMAGE_BYTES
    else:
        max_bytes = MAX_FILE_BYTES

    if len(data) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        return jsonify({"ok": False, "error": f"File is too large ({len(data)//(1024*1024)}MB) — mesh links cap at {limit_mb}MB"}), 413

    try:
        link = network.get_or_create_link(dest_hex)
    except network.NoPathError:
        return jsonify({"ok": False, "error": "No known path to that peer yet — requested one, try again shortly"}), 202
    except network.NoIdentityError:
        return jsonify({"ok": False, "error": "Could not resolve that peer's identity"}), 404
    except network.LinkTimeoutError:
        return jsonify({"ok": False, "error": "Timed out establishing a link to that peer"}), 504

    ext = MEDIA_EXT_BY_MIME.get(mime, "bin")
    mid = str(uuid.uuid4())
    filename = f"{mid}.{ext}"

    if kind in ("image", "video"):
        save_dir = IMAGES_DIR
        url_path = f"/api/images/{filename}"
    else:
        save_dir = FILES_DIR
        url_path = f"/api/files/{filename}"

    with open(os.path.join(save_dir, filename), "wb") as f:
        f.write(data)

    if kind in ("audio", "file"):
        body = json.dumps({"url": url_path, "name": original_name})
    else:
        body = url_path

    insert_message(mid, dest_hex, None, "out", kind, body, "sending", time.time())

    def _concluded(resource):
        update_message_status(mid, "sent" if resource.status == RNS.Resource.COMPLETE else "failed")

    RNS.Resource(data, link, metadata={"kind": kind, "ext": ext, "mime": mime, "name": original_name}, callback=_concluded)
    return jsonify({"ok": True, "mid": mid, "kind": kind})

@app.route("/api/send-image", methods=["POST"])
def api_send_image():
    return api_send_media()

@app.route("/api/images/<path:filename>", methods=["GET"])
def api_get_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

@app.route("/api/files/<path:filename>", methods=["GET"])
def api_get_file(filename):
    inline = request.args.get("inline", "0") == "1"
    return send_from_directory(FILES_DIR, filename, as_attachment=not inline)

@app.route("/api/location", methods=["POST"])
def api_share_location():
    data = request.get_json(force=True) or {}
    lat, lon = data.get("lat"), data.get("lon")
    acc = data.get("accuracy")
    target = data.get("share_with") or {}
    if lat is None or lon is None:
        return jsonify({"ok": False, "error": "lat/lon required"}), 400

    mid = str(uuid.uuid4())
    ts = time.time()
    envelope = {"mid": mid, "from": network.destination.hash.hex(), "type": "location", "lat": lat, "lon": lon, "acc": acc, "ts": ts}

    if "peer" in target:
        ok, err = network.try_send_envelope_to_peer(target["peer"], envelope)
        if not ok:
            return jsonify({"ok": False, "error": err}), 202
    elif "group" in target:
        with network.groups_lock:
            group = network.active_groups.get(target["group"])
        if not group:
            return jsonify({"ok": False, "error": "not subscribed to this group"}), 404
        ciphertext = group["fernet"].encrypt(json.dumps(envelope).encode("utf-8"))
        RNS.Packet(group["destination"], ciphertext).send()
    else:
        return jsonify({"ok": False, "error": "share_with must include a peer or group"}), 400

    return jsonify({"ok": True})

@app.route("/api/locations", methods=["GET"])
def api_get_locations():
    with db_lock:
        rows = conn.execute(
            "SELECT peer_hash, lat, lon, accuracy_m, shared_with, ts FROM locations"
        ).fetchall()
    return jsonify([
        {"peer_hash": r[0], "lat": r[1], "lon": r[2], "accuracy_m": r[3], "shared_with": r[4], "ts": r[5]}
        for r in rows
    ])

@app.route("/api/groups", methods=["GET"])
def api_list_groups():
    with db_lock:
        rows = conn.execute("SELECT group_id, name FROM groups").fetchall()
    return jsonify([{"group_id": r[0], "name": r[1]} for r in rows])

@app.route("/api/groups", methods=["POST"])
def api_create_group():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "Unnamed Group").strip()
    group_id = uuid.uuid4().hex[:12]
    key = Fernet.generate_key()

    with db_lock:
        conn.execute(
            "INSERT INTO groups(group_id,name,key,created_at) VALUES (?,?,?,?)",
            (group_id, name, key.decode(), time.time()),
        )
        conn.commit()

    network.subscribe_group(group_id, name, key.decode())
    return jsonify({"ok": True, "group_id": group_id, "name": name, "invite": network.encode_invite(group_id, name, key.decode())})

@app.route("/api/groups/join", methods=["POST"])
def api_join_group():
    data = request.get_json(force=True) or {}
    invite = (data.get("invite") or "").strip()
    try:
        group_id, name, key_str = network.decode_invite(invite)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid invite code"}), 400

    with db_lock:
        conn.execute(
            "INSERT OR REPLACE INTO groups(group_id,name,key,created_at) VALUES (?,?,?,?)",
            (group_id, name, key_str, time.time()),
        )
        conn.commit()

    network.subscribe_group(group_id, name, key_str)
    return jsonify({"ok": True, "group_id": group_id, "name": name})

@app.route("/api/groups/<group_id>/invite", methods=["GET"])
def api_group_invite(group_id):
    with db_lock:
        row = conn.execute("SELECT name, key FROM groups WHERE group_id=?", (group_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "unknown group"}), 404
    return jsonify({"ok": True, "invite": network.encode_invite(group_id, row[0], row[1])})

@app.route("/api/groups/<group_id>/send", methods=["POST"])
def api_group_send(group_id):
    data = request.get_json(force=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "message required"}), 400

    with network.groups_lock:
        group = network.active_groups.get(group_id)
    if not group:
        return jsonify({"ok": False, "error": "not subscribed to this group"}), 404

    mid = str(uuid.uuid4())
    ts = time.time()
    envelope = {"mid": mid, "from": network.destination.hash.hex(), "type": "text", "body": text, "ts": ts}
    ciphertext = group["fernet"].encrypt(json.dumps(envelope).encode("utf-8"))
    RNS.Packet(group["destination"], ciphertext).send()
    insert_message(mid, None, group_id, "out", "text", text, "sent", ts)
    return jsonify({"ok": True, "mid": mid})

from bundler import build_bundle_zip
@app.route("/download/bundle", methods=["GET"])
def download_bundle():
    buf = build_bundle_zip()
    return send_file(buf, as_attachment=True, download_name="centr_bundle.zip", mimetype="application/zip")

@app.route("/download/apk", methods=["GET"])
def download_apk():
    apk_path = os.path.join(APK_DIR, APK_FILENAME)
    if not os.path.isfile(apk_path):
        return jsonify({
            "ok": False,
            "error": "The Android engine hasn't been built yet. See static/bin/PLACEHOLDER_README.txt "
                     "for how to build and place centr.apk here."
        }), 404
    return send_file(apk_path, as_attachment=True, download_name=APK_FILENAME, mimetype="application/vnd.android.package-archive")

@app.route("/download/termux", methods=["GET"])
def download_termux():
    """
    Fix #2: during an actual blackout, a device may have neither Termux nor
    internet access to get it. Since Termux is GPLv3 and freely
    redistributable (unlike the deprecated, no-longer-updated Play Store
    build), we bundle its APK here and serve it the same way as centr.apk -
    so the very first hop can hand out Termux itself, no app store needed.
    """
    termux_path = os.path.join(APK_DIR, TERMUX_APK_FILENAME)
    if not os.path.isfile(termux_path):
        return jsonify({
            "ok": False,
            "error": "Termux hasn't been bundled on this device yet. Download the "
                     "F-Droid build of Termux (GPLv3, freely redistributable) and "
                     "place it at static/bin/termux.apk - see "
                     "static/bin/PLACEHOLDER_README.txt."
        }), 404
    return send_file(termux_path, as_attachment=True, download_name="termux.apk", mimetype="application/vnd.android.package-archive")

@app.route("/download/exe", methods=["GET"])
def download_exe():
    exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.join(APK_DIR, EXE_FILENAME)
    if not os.path.isfile(exe_path):
        return jsonify({
            "ok": False,
            "error": "The Windows engine hasn't been built yet. See static/bin/PLACEHOLDER_README.txt "
                     "for how to build and place centr_windows.exe here."
        }), 404
    return send_file(exe_path, as_attachment=True, download_name=EXE_FILENAME, mimetype="application/vnd.microsoft.portable-executable")
