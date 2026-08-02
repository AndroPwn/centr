import os
import sys
import json
import time
import uuid
import threading
import base64

if getattr(sys, "frozen", False):
    import glob as _glob
    _RNS_INTERFACE_MODULES = [
        "Interface", "TCPInterface", "LocalInterface", "AutoInterface",
        "UDPInterface", "I2PInterface", "RNodeInterface", "RNodeMultiInterface",
        "SerialInterface", "KISSInterface", "AX25KISSInterface",
        "PipeInterface", "BackboneInterface", "WeaveInterface",
    ]
    _real_glob_glob = _glob.glob

    def _rns_frozen_safe_glob(pathname, *args, **kwargs):
        result = _real_glob_glob(pathname, *args, **kwargs)
        if not result and pathname.replace("\\", "/").rstrip("/").endswith(
            ("RNS/Interfaces/*.py", "RNS/Interfaces/*.pyc")
        ):
            base = os.path.dirname(pathname)
            ext = ".pyc" if pathname.endswith(".pyc") else ".py"
            result = [os.path.join(base, name + ext) for name in _RNS_INTERFACE_MODULES]
        return result

    _glob.glob = _rns_frozen_safe_glob

import RNS
from cryptography.fernet import Fernet
from config import APP_NAME, ASPECT, RETICULUM_CONFIG_DIR, IDENTITY_PATH, IMAGES_DIR, FILES_DIR
from database import insert_message, update_message_status, already_seen, upsert_location, get_max_receive_size, db_lock, conn, get_display_name, upsert_peer_announced_name, DISPLAY_NAME_MAX_LEN

reticulum = None
identity = None
destination = None
CURRENT_TRANSPORT_ENABLED = False

active_groups = {}
groups_lock = threading.Lock()

link_pool = {}
link_pool_lock = threading.Lock()
link_identities = {}

class NoPathError(Exception):
    pass

class NoIdentityError(Exception):
    pass

class LinkTimeoutError(Exception):
    pass

def encode_invite(group_id, name, key_str):
    payload = json.dumps({"g": group_id, "n": name, "k": key_str}).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")

def decode_invite(invite_str):
    payload = json.loads(base64.urlsafe_b64decode(invite_str.encode("ascii")).decode("utf-8"))
    return payload["g"], payload["n"], payload["k"]

def write_reticulum_config(configdir, enable_transport, listen_port, connect_to):
    """
    connect_to may be:
      - None / "" -> listen only, no outbound peer
      - a single "host:port" string (legacy/simple case)
      - a list/tuple of "host:port" strings

    Fix #4: a phone bridging a Bluetooth-PAN peer and a Wi-Fi peer at once
    (the "hotspot chain" scenario) needs *multiple* simultaneous outbound
    interfaces in its Reticulum config, not just one. Since Bluetooth PAN
    presents itself to the OS as a normal IP link (fix #3's cheap first
    step), each of those links is just another TCPClientInterface entry
    here - no new interface *type* is needed to support multiple links at
    once, just multiple stanzas, each with a unique section name.
    """
    if connect_to is None:
        targets = []
    elif isinstance(connect_to, str):
        targets = [t.strip() for t in connect_to.split(",") if t.strip()]
    else:
        targets = [t.strip() for t in connect_to if t and t.strip()]

    lines = [
        "[reticulum]",
        f"  enable_transport = {'Yes' if enable_transport else 'No'}",
        "  share_instance = No",
        "  instance_name = centr",
        "",
        "[logging]",
        "  loglevel = 3",
        "",
        "[interfaces]",
        # Zero-config discovery: devices on the same Wi-Fi/hotspot find each
        # other automatically over UDP multicast, no IP/port entry needed.
        # This is what makes "just run the exe" actually work for two
        # people on the same hotspot with no setup step.
        "  [[centr Auto Discovery]]",
        "    type = AutoInterface",
        "    enabled = Yes",
        "    group_id = centr-mesh",
        "",
        "  [[centr Listen]]",
        "    type = TCPServerInterface",
        "    enabled = Yes",
        "    listen_ip = 0.0.0.0",
        f"    listen_port = {listen_port}",
    ]
    for idx, target in enumerate(targets):
        host, _, port_str = target.partition(":")
        port = port_str.strip() or str(listen_port)
        section_name = "centr Connect" if idx == 0 else f"centr Connect {idx + 1}"
        lines += [
            "",
            f"  [[{section_name}]]",
            "    type = TCPClientInterface",
            "    enabled = Yes",
            f"    target_host = {host.strip()}",
            f"    target_port = {port}",
        ]
    lines.append("")

    with open(os.path.join(configdir, "config"), "w") as f:
        f.write("\n".join(lines))

def patch_config_transport_flag(configdir, enabled):
    path = os.path.join(configdir, "config")
    if not os.path.isfile(path):
        return
    with open(path) as f:
        lines = f.readlines()

    found = False
    out = []
    for line in lines:
        if line.strip().lower().startswith("enable_transport"):
            out.append(f"  enable_transport = {'Yes' if enabled else 'No'}\n")
            found = True
        else:
            out.append(line)

    if not found:
        inserted = []
        placed = False
        for line in out:
            inserted.append(line)
            if line.strip().lower() == "[reticulum]" and not placed:
                inserted.append(f"  enable_transport = {'Yes' if enabled else 'No'}\n")
                placed = True
        out = inserted if placed else out + [f"\n[reticulum]\n  enable_transport = {'Yes' if enabled else 'No'}\n"]

    with open(path, "w") as f:
        f.writelines(out)

def try_send_envelope_to_peer(dest_hex, envelope):
    try:
        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        if len(dest_hex) != dest_len:
            return False, f"destination must be {dest_len} hex characters"
        destination_hash = bytes.fromhex(dest_hex)
    except ValueError:
        return False, "destination is not valid hex"

    if not RNS.Transport.has_path(destination_hash):
        RNS.Transport.request_path(destination_hash)
        return False, "no known path yet — requested one"

    peer_identity = RNS.Identity.recall(destination_hash)
    if peer_identity is None:
        return False, "peer identity not resolved yet"

    out_dest = RNS.Destination(
        peer_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT
    )
    RNS.Packet(out_dest, json.dumps(envelope).encode("utf-8")).send()
    return True, None

def retry_worker():
    global destination
    while True:
        time.sleep(5)
        if destination is None:
            continue
        with db_lock:
            rows = conn.execute(
                "SELECT id, peer_hash, body, ts FROM messages "
                "WHERE direction='out' AND status='queued' AND group_id IS NULL"
            ).fetchall()
        for mid, peer_hash, body, ts in rows:
            envelope = {"mid": mid, "from": destination.hash.hex(), "type": "text", "body": body, "ts": ts}
            ok, _err = try_send_envelope_to_peer(peer_hash, envelope)
            if ok:
                update_message_status(mid, "sent")

def packet_received(message, packet):
    try:
        envelope = json.loads(message.decode("utf-8"))
    except Exception:
        return

    mid = envelope.get("mid") or uuid.uuid4().hex
    if already_seen(mid):
        return

    sender = envelope.get("from", "unknown")
    mtype = envelope.get("type", "text")
    ts = envelope.get("ts", time.time())

    if mtype == "location":
        upsert_location(sender, envelope.get("lat"), envelope.get("lon"),
                         envelope.get("acc"), shared_with=f"peer:{sender}", ts=ts)
        insert_message(mid, sender, None, "in", "location", None, "received", ts)
    else:
        insert_message(mid, sender, None, "in", "text", envelope.get("body"), "received", ts)

def resource_callback(resource, link):
    max_size = get_max_receive_size()
    if resource.get_transfer_size() <= max_size:
        return True
    return False

def client_connected(link):
    link.set_link_closed_callback(client_disconnected)
    link.set_resource_strategy(RNS.Link.ACCEPT_APP)
    link.set_resource_callback(lambda resource: resource_callback(resource, link))
    link.set_remote_identified_callback(remote_identified)
    link.set_resource_concluded_callback(lambda resource: resource_concluded(resource, link))

def client_disconnected(link):
    with link_pool_lock:
        link_identities.pop(link, None)

def remote_identified(link, identity_obj):
    remote_dest = RNS.Destination(identity_obj, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    with link_pool_lock:
        link_identities[link] = remote_dest.hash.hex()

def resource_concluded(resource, link):
    if resource.status != RNS.Resource.COMPLETE:
        return
    data = resource.data.read()
    meta = resource.metadata or {}
    kind = str(meta.get("kind", "image")).lower()
    if kind not in ("image", "video", "audio", "file"):
        kind = "file"
    ext = str(meta.get("ext", "bin")).lower().lstrip(".")
    ext = "".join(ch for ch in ext if ch.isalnum()) or "bin"
    original_name = meta.get("name", f"file.{ext}")
    filename = f"{uuid.uuid4().hex}.{ext}"

    # Decide storage directory and URL path based on kind
    if kind in ("image", "video"):
        save_dir = IMAGES_DIR
        url_path = f"/api/images/{filename}"
    else:
        save_dir = FILES_DIR
        url_path = f"/api/files/{filename}"

    with open(os.path.join(save_dir, filename), "wb") as f:
        f.write(data)

    with link_pool_lock:
        sender = link_identities.get(link, "unknown")

    mid = str(uuid.uuid4())
    # For non-media files, store both the URL and original name as JSON
    if kind in ("audio", "file"):
        body = json.dumps({"url": url_path, "name": original_name})
    else:
        body = url_path
    insert_message(mid, sender, None, "in", kind, body, "received", time.time())

def get_or_create_link(peer_hash_hex):
    global identity
    with link_pool_lock:
        existing = link_pool.get(peer_hash_hex)
        if existing is not None and existing.status == RNS.Link.ACTIVE:
            return existing

    try:
        peer_hash = bytes.fromhex(peer_hash_hex)
    except ValueError:
        raise NoIdentityError()

    if not RNS.Transport.has_path(peer_hash):
        RNS.Transport.request_path(peer_hash)
        raise NoPathError()

    peer_identity = RNS.Identity.recall(peer_hash)
    if peer_identity is None:
        raise NoIdentityError()

    out_dest = RNS.Destination(peer_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    link = RNS.Link(out_dest)

    waited = 0.0
    while link.status != RNS.Link.ACTIVE and waited < 10.0:
        time.sleep(0.1)
        waited += 0.1

    if link.status != RNS.Link.ACTIVE:
        raise LinkTimeoutError()

    link.identify(identity)

    with link_pool_lock:
        link_pool[peer_hash_hex] = link

    return link

class BridgeAnnounceHandler:
    def __init__(self, aspect_filter=None):
        self.aspect_filter = aspect_filter

    def received_announce(self, destination_hash, announced_identity, app_data):
        hex_hash = destination_hash.hex()
        announced_name = None
        if app_data:
            try:
                announced_name = app_data.decode("utf-8", errors="ignore")[:DISPLAY_NAME_MAX_LEN].strip() or None
            except Exception:
                announced_name = None
        upsert_peer_announced_name(hex_hash, announced_name, time.time())

def subscribe_group(group_id, name, key_str):
    fernet = Fernet(key_str.encode() if isinstance(key_str, str) else key_str)
    group_destination = RNS.Destination(
        None, RNS.Destination.IN, RNS.Destination.PLAIN, APP_NAME, "group", group_id
    )

    def _cb(message, packet, _gid=group_id, _fernet=fernet):
        group_packet_received(_gid, _fernet, message, packet)

    group_destination.set_packet_callback(_cb)

    with groups_lock:
        active_groups[group_id] = {"destination": group_destination, "fernet": fernet, "name": name}

def group_packet_received(group_id, fernet, message, packet):
    try:
        plaintext = fernet.decrypt(message)
        envelope = json.loads(plaintext.decode("utf-8"))
    except Exception:
        return

    mid = envelope.get("mid") or uuid.uuid4().hex
    if already_seen(mid):
        return

    sender = envelope.get("from", "unknown")
    ts = envelope.get("ts", time.time())
    mtype = envelope.get("type", "text")

    if mtype == "location":
        upsert_location(sender, envelope.get("lat"), envelope.get("lon"),
                         envelope.get("acc"), shared_with=f"group:{group_id}", ts=ts)
        insert_message(mid, sender, group_id, "in", "location", None, "received", ts)
    else:
        insert_message(mid, sender, group_id, "in", "text", envelope.get("body"), "received", ts)

def _current_app_data():
    name = get_display_name()
    return name.encode("utf-8") if name else None

def reannounce():
    if destination is not None:
        destination.announce(app_data=_current_app_data())

def start_reticulum():
    global reticulum, identity, destination, CURRENT_TRANSPORT_ENABLED
    
    os.makedirs(RETICULUM_CONFIG_DIR, exist_ok=True)

    listen_port = int(os.environ.get("centr_LISTEN_PORT", 4242))
    # Comma-separated for multi-hop relaying (fix #4), e.g.
    # centr_CONNECT_TO="192.168.44.1:4242,192.168.43.1:4242" to bridge a
    # Bluetooth-PAN peer and a Wi-Fi hotspot peer from the same device.
    connect_to = os.environ.get("centr_CONNECT_TO", "").strip() or None

    with db_lock:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='relay_enabled_pending'"
        ).fetchone()
    desired_transport = (row[0] == "1") if row else False

    write_reticulum_config(RETICULUM_CONFIG_DIR, desired_transport, listen_port, connect_to)

    reticulum = RNS.Reticulum(configdir=RETICULUM_CONFIG_DIR)
    CURRENT_TRANSPORT_ENABLED = desired_transport

    if os.path.isfile(IDENTITY_PATH):
        identity = RNS.Identity.from_file(IDENTITY_PATH)
        if identity is None:
            identity = RNS.Identity()
            identity.to_file(IDENTITY_PATH)
    else:
        identity = RNS.Identity()
        identity.to_file(IDENTITY_PATH)

    destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    destination.set_proof_strategy(RNS.Destination.PROVE_ALL)
    destination.set_packet_callback(packet_received)
    destination.set_link_established_callback(client_connected)

    RNS.Transport.register_announce_handler(BridgeAnnounceHandler(aspect_filter=f"{APP_NAME}.{ASPECT}"))
    destination.announce(app_data=_current_app_data())

    with db_lock:
        rows = conn.execute("SELECT group_id, name, key FROM groups").fetchall()
    for group_id, name, key_str in rows:
        subscribe_group(group_id, name, key_str)

    threading.Thread(target=retry_worker, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    print("\n centr local address: " + RNS.prettyhexrep(destination.hash))
    print(f"   Relay/transport: {'ENABLED' if CURRENT_TRANSPORT_ENABLED else 'disabled'} "
          f"(change in Settings tab — requires restart to apply)")
    print(f"   Listening for other devices on port {listen_port}"
          + (f"; connected out to {connect_to}" if connect_to else " (no outbound peer configured)"))
    print(f"   Dashboard: http://127.0.0.1:{port}  (or http://<this-device-ip>:{port} for neighbors on your hotspot)\n")
