import os

APP_NAME = "centr"
ASPECT = "message"

APP_DIR = os.environ.get("centr_HOME") or os.path.expanduser("~/.centr")
RETICULUM_CONFIG_DIR = os.path.join(APP_DIR, "reticulum")
IDENTITY_PATH = os.path.join(APP_DIR, "identity.key")
IMAGES_DIR = os.path.join(APP_DIR, "images")
FILES_DIR = os.path.join(APP_DIR, "files")

MEDIA_EXT_BY_MIME = {
    # Images
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    # Video
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    # Audio
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/webm": "webm",
    "audio/aac": "aac",
    "audio/flac": "flac",
    "audio/x-m4a": "m4a",
    "audio/mp4": "m4a",
    # Documents
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    # Archives
    "application/zip": "zip",
    "application/x-tar": "tar",
    "application/gzip": "gz",
    "application/x-7z-compressed": "7z",
    "application/x-rar-compressed": "rar",
    # Text / code
    "text/plain": "txt",
    "text/csv": "csv",
    "text/html": "html",
    "text/markdown": "md",
    "application/json": "json",
    "application/xml": "xml",
    # Misc
    "application/octet-stream": "bin",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024

def media_kind_from_mime(mime):
    if not mime:
        return None
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"

DB_PATH = os.path.join(APP_DIR, "centr.db")
SESSION_KEY_PATH = os.path.join(APP_DIR, "session.key")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
APK_DIR = os.path.join(STATIC_DIR, "bin")
APK_FILENAME = "centr.apk"
EXE_FILENAME = "centr_windows.exe"
TERMUX_APK_FILENAME = "termux.apk"
WHEELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wheels")

for d in (APP_DIR, IMAGES_DIR, FILES_DIR, APK_DIR):
    os.makedirs(d, exist_ok=True)

PASSCODE_SETTINGS_KEY = "passcode_hash"
NO_AUTH = os.environ.get("centr_NO_AUTH", "0") == "1"
