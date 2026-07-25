import os
import sys
import io
import zipfile
from config import STATIC_DIR, APK_DIR, APK_FILENAME, EXE_FILENAME, WHEELS_DIR, TERMUX_APK_FILENAME

SOURCE_FILES = ["config.py", "database.py", "auth.py", "network.py", "bundler.py", "app.py", "routes.py", "main.py"]


def _source_root():
    """
    Directory that actually contains our .py source files.

    In a normal `python main.py` run this is just the folder next to this
    file. Inside a PyInstaller --onefile build, __file__ points into a
    temporary extraction path that does NOT contain the original .py
    sources (only the compiled/frozen bytecode) - so we fall back to the
    bundled data directory (sys._MEIPASS), which build_windows_exe.ps1
    populates via --add-data for exactly this purpose.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = os.path.join(meipass, "pysrc")
            if os.path.isdir(candidate):
                return candidate
    return os.path.dirname(os.path.abspath(__file__))

TERMUX_INSTALL_SH = """#!/data/data/com.termux/files/usr/bin/bash
set -e
echo "Installing Python..."
pkg update -y >/dev/null 2>&1 || true
pkg install -y python >/dev/null
pip install --upgrade pip >/dev/null

if [ -d "wheels" ] && [ -n "$(ls -A wheels 2>/dev/null)" ]; then
  echo "Found bundled packages - installing fully offline..."
  pip install --no-index --find-links=wheels -r requirements.txt || {
    echo "Offline install failed (wheels likely built for a different CPU/Python"
    echo "than this phone's Termux - Android arm64 wheels rarely match a laptop's"
    echo "wheels). Falling back to a normal internet install...";
    pip install rns flask flask-cors cryptography;
  }
else
  echo "No bundled packages found - installing from the internet..."
  pip install rns flask flask-cors cryptography
fi

echo ""
echo "Setup complete. Starting centr..."
echo "Once running, open this phone's own browser to http://127.0.0.1:5000"
echo "The passcode will be printed below the first time it starts - save it."
echo ""
python main.py
"""

LAPTOP_INSTALL_SH = """#!/usr/bin/env bash
set -e
if [ -d "wheels" ] && [ -n "$(ls -A wheels 2>/dev/null)" ]; then
  echo "Found bundled packages - installing fully offline..."
  pip3 install --break-system-packages --no-index --find-links=wheels -r requirements.txt 2>/dev/null \\
    || pip3 install --no-index --find-links=wheels -r requirements.txt
else
  echo "No bundled packages found - installing from the internet..."
  pip3 install --break-system-packages rns flask flask-cors cryptography 2>/dev/null \\
    || pip3 install rns flask flask-cors cryptography
fi
echo ""
echo "Starting centr - open http://127.0.0.1:5000 in your browser."
echo "The device passcode prints below the first time it starts - save it."
echo ""
python3 main.py
"""

LAPTOP_INSTALL_PS1 = """if ((Test-Path "wheels") -and (Get-ChildItem "wheels" -ErrorAction SilentlyContinue)) {
    Write-Host "Found bundled packages - installing fully offline..."
    pip install --no-index --find-links=wheels -r requirements.txt
} else {
    Write-Host "No bundled packages found - installing from the internet..."
    pip install rns flask flask-cors cryptography
}
Write-Host ""
Write-Host "Starting centr - open http://127.0.0.1:5000 in your browser."
Write-Host "The device passcode prints below the first time it starts - save it."
Write-Host ""
python main.py
"""

BUNDLE_README = """centr - Offline Install Bundle
===================================

You got this file with zero internet - someone on your Wi-Fi/hotspot right
now is running centr, and this bundle is its own source code, downloaded
straight from their device. Once you install it, YOUR device becomes a new
source too - anyone who connects to *your* hotspot can pull this same
bundle from you next.

If a "wheels" folder is included here, it contains the actual Python
package files (Flask, Reticulum, etc.) pre-downloaded by whoever built this
bundle while they still had internet - so this install needs ZERO internet
access, not even for pip. If there's no wheels folder, or the offline
install fails (this most often happens between very different devices,
e.g. wheels from a Windows laptop won't work on an Android phone's Termux
- see note below), the installer automatically falls back to a normal
`pip install` from PyPI, which does need internet.

If a "bin" folder is included here, it contains prebuilt binaries
(centr_windows.exe, centr.apk, and/or termux.apk) collected from the
device you got this bundle from, so you can re-serve them to the *next*
device in the chain even if you yourself installed from source.

To install:

  Android (via Termux):
    0. Don't have Termux? If bin/termux.apk is in this folder, install
       that (Settings -> allow installs from unknown sources, then tap
       the APK). Otherwise get it from F-Droid or a friend's copy - do
       NOT use the Play Store build, it's deprecated and no longer
       updated.
    1. Copy this whole folder into Termux's storage.
    2. Run:  bash install_termux.sh
    3. Leave Termux running in the background; open a browser to
       http://127.0.0.1:5000

  Laptop (Mac/Linux):
    1. Make sure Python 3 is installed.
    2. Run:  bash install_laptop.sh

  Laptop (Windows):
    1. Make sure Python 3 is installed (python.org, or pre-installed).
    2. Right-click install_laptop.ps1 -> Run with PowerShell.

Either way, the very first thing it prints is a 6-digit device passcode -
write it down, you'll need it to open the dashboard. You can change it
later from the Settings tab.

Once it's running, turn ON your device's own hotspot (Settings) so the next
person can connect to you and pull this exact bundle from
http://<your-ip>:5000/download/bundle - no app store, no internet, ever,
at any step of the chain (wheels included).

Why wheels don't always transfer between devices: most of these packages
are pure Python and work anywhere, but "cryptography" contains compiled
code specific to one OS + CPU architecture + Python version. Wheels
downloaded on a Windows laptop will install fine on another Windows laptop
with a similar Python version, but will NOT work on an Android phone or a
Mac. If you're prepping bundles for a mixed fleet of devices, run the
wheel-download prep step separately on one machine of each OS/platform you
expect to distribute to.

One honest caveat: some device, somewhere, still had to have internet
access at some point to originally get centr, Termux, and (if used) the
wheels - that first step can't be skipped. What's zero-internet is
everything AFTER that: every device downstream of that first one gets the
whole app, Termux, and its dependencies purely over local Wi-Fi/hotspot,
no internet required at any later hop.
"""

def build_bundle_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # Write core python files. Use _source_root() rather than assuming
        # __file__'s directory, since that assumption breaks inside a
        # frozen PyInstaller .exe (see _source_root docstring / fix #1).
        base_dir = _source_root()
        missing = []
        for file in SOURCE_FILES:
            path = os.path.join(base_dir, file)
            if os.path.exists(path):
                zf.write(path, file)
            else:
                missing.append(file)

        req_path = os.path.join(base_dir, "requirements.txt")
        if os.path.isfile(req_path):
            zf.write(req_path, "requirements.txt")

        for root, _dirs, files in os.walk(STATIC_DIR):
            for fname in files:
                if fname in (APK_FILENAME, EXE_FILENAME, TERMUX_APK_FILENAME):
                    continue
                full = os.path.join(root, fname)
                arcname = os.path.join("static", os.path.relpath(full, STATIC_DIR))
                zf.write(full, arcname)

        if os.path.isdir(WHEELS_DIR):
            for fname in os.listdir(WHEELS_DIR):
                full = os.path.join(WHEELS_DIR, fname)
                if os.path.isfile(full):
                    zf.write(full, os.path.join("wheels", fname))

        # Fix #6: propagate binaries alongside source. Without this, a
        # device that only ever received the *source* bundle (rather than
        # running the original .exe/.apk itself) has nothing to re-serve
        # at /download/exe, /download/apk, or /download/termux to the next
        # hop in a hotspot chain, even though an earlier device in the
        # chain had one. Bundling them here (when present on disk) keeps
        # binaries and source travelling together automatically.
        for fname in (APK_FILENAME, EXE_FILENAME, TERMUX_APK_FILENAME):
            full = os.path.join(APK_DIR, fname)
            if os.path.isfile(full):
                zf.write(full, os.path.join("bin", fname))

        zf.writestr("install_termux.sh", TERMUX_INSTALL_SH)
        zf.writestr("install_laptop.sh", LAPTOP_INSTALL_SH)
        zf.writestr("install_laptop.ps1", LAPTOP_INSTALL_PS1)
        zf.writestr("README.txt", BUNDLE_README)

        if missing:
            zf.writestr(
                "BUNDLE_WARNING.txt",
                "This bundle is missing source file(s): " + ", ".join(missing) + "\n"
                "This should only happen for a frozen .exe build that wasn't packaged\n"
                "with --add-data pysrc (see build_windows_exe.ps1). The install scripts\n"
                "in this zip will not work until that's fixed - re-download from a\n"
                "device running from source, or rebuild the .exe correctly.\n",
            )

    buf.seek(0)
    return buf
