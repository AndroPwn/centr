import sqlite3
import threading
from config import DB_PATH, PASSCODE_SETTINGS_KEY

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
db_lock = threading.Lock()

def init_db():
    with db_lock:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS peers (
            hash TEXT PRIMARY KEY,
            nickname TEXT,
            announced_name TEXT,
            last_seen REAL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            group_id TEXT,
            peer_hash TEXT,
            direction TEXT,
            mtype TEXT,
            body TEXT,
            status TEXT,
            ts REAL
        );
        CREATE TABLE IF NOT EXISTS seen_ids (
            message_id TEXT PRIMARY KEY,
            first_seen_at REAL
        );
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            name TEXT,
            key TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS locations (
            peer_hash TEXT PRIMARY KEY,
            lat REAL,
            lon REAL,
            accuracy_m REAL,
            shared_with TEXT,
            ts REAL
        );
        """)
        # Migrate DBs created before announced_name existed
        cols = [r[1] for r in conn.execute("PRAGMA table_info(peers)").fetchall()]
        if "announced_name" not in cols:
            conn.execute("ALTER TABLE peers ADD COLUMN announced_name TEXT")
        conn.commit()

DISPLAY_NAME_SETTINGS_KEY = "display_name"
DISPLAY_NAME_MAX_LEN = 64

def get_display_name():
    with db_lock:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (DISPLAY_NAME_SETTINGS_KEY,)
        ).fetchone()
    return row[0] if row else ""

def set_display_name(name):
    name = (name or "")[:DISPLAY_NAME_MAX_LEN]
    with db_lock:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (DISPLAY_NAME_SETTINGS_KEY, name),
        )
        conn.commit()
    return name

def upsert_peer_announced_name(peer_hash, announced_name, ts):
    with db_lock:
        conn.execute(
            "INSERT INTO peers(hash,nickname,announced_name,last_seen) VALUES (?,NULL,?,?) "
            "ON CONFLICT(hash) DO UPDATE SET announced_name=excluded.announced_name, "
            "last_seen=excluded.last_seen",
            (peer_hash, announced_name, ts),
        )
        conn.commit()

def insert_message(mid, peer_hash, group_id, direction, mtype, body, status, ts):
    with db_lock:
        conn.execute(
            "INSERT OR REPLACE INTO messages(id,group_id,peer_hash,direction,mtype,body,status,ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (mid, group_id, peer_hash, direction, mtype, body, status, ts),
        )
        conn.commit()

def update_message_status(mid, status):
    with db_lock:
        conn.execute("UPDATE messages SET status=? WHERE id=?", (status, mid))
        conn.commit()

def already_seen(mid):
    with db_lock:
        cur = conn.execute(
            "INSERT OR IGNORE INTO seen_ids(message_id, first_seen_at) VALUES (?,?)",
            (mid, __import__('time').time()),
        )
        conn.commit()
        return cur.rowcount == 0

def upsert_location(peer_hash, lat, lon, acc, shared_with, ts):
    with db_lock:
        conn.execute(
            "INSERT INTO locations(peer_hash,lat,lon,accuracy_m,shared_with,ts) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(peer_hash) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, "
            "accuracy_m=excluded.accuracy_m, shared_with=excluded.shared_with, ts=excluded.ts",
            (peer_hash, lat, lon, acc, shared_with, ts),
        )
        conn.commit()

def get_passcode_hash():
    with db_lock:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (PASSCODE_SETTINGS_KEY,)
        ).fetchone()
    return row[0] if row else None

def set_passcode_hash(pw_hash):
    with db_lock:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (PASSCODE_SETTINGS_KEY, pw_hash),
        )
        conn.commit()

def get_max_receive_size():
    with db_lock:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='max_recv_bytes'"
        ).fetchone()
    # Default to 25MB if not set
    return int(row[0]) if row else 25 * 1024 * 1024

def set_max_receive_size(size_bytes):
    with db_lock:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('max_recv_bytes', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(int(size_bytes)),),
        )
        conn.commit()
