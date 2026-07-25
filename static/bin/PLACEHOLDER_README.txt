This folder is where bridge.py looks for the packaged Android app:

    static/bin/centr.apk

-------------------------------------------------------------------------

TERMUX: static/bin/termux.apk (so a blackout can hand out Termux itself)

If a new Android device doesn't already have Termux installed and there's
no internet, there's currently no way to get it without this file.
Termux is GPLv3 and freely redistributable (unlike the deprecated,
no-longer-updated Play Store build), so it can legally be bundled here.

To make /download/termux work:
  1. On a machine with internet, download the latest Termux APK from
     either F-Droid (https://f-droid.org/packages/com.termux/) or the
     GitHub releases page (https://github.com/termux/termux-app/releases)
     - use the .apk matching the target device's CPU architecture
       (arm64-v8a covers the large majority of modern Android phones).
  2. Save it here as exactly: static/bin/termux.apk
  3. /download/termux will start serving it automatically, and it'll also
     be included under bin/ in every /download/bundle zip from then on -
     no code changes needed either way.


There is no real APK in here yet — I didn't fabricate a placeholder binary,
because a fake/empty .apk would just look like a broken or scammy download
to whoever taps the button. Right now /download/apk correctly returns a
clear "not built yet" message instead of a broken file.

To make the download button actually work, you need to produce a real,
signed Android package that runs this same bridge.py (Flask + Reticulum +
SQLite) in the background, plus a WebView pointed at http://127.0.0.1:5000.
Realistic options, fastest first:

1. Termux + a startup script (fastest to get working for a hackathon)
   - Ship a small script that installs Termux from F-Droid (or bundles the
     Termux APK directly, since Termux itself is open source and
     redistributable), then runs `pip install rns flask flask-cors` and
     `python bridge.py` on first launch.
   - Pro: you already have working Python code, zero rewrite.
   - Con: not a "real" app icon/experience — it's a terminal running a
     server, with the browser as the actual UI.

2. WebView wrapper + embedded Python runtime (Chaquopy or Kivy/Buildozer)
   - Chaquopy (Android Studio + Gradle plugin) lets you run this exact
     bridge.py inside a normal Android app process, with a WebView loading
     http://127.0.0.1:5000 as the UI. This is the "proper app" version of
     what's described in the architecture doc.
   - Buildozer/python-for-android is the alternative toolchain; both are
     real, working paths, but both need Android Studio/SDK/Gradle and
     several hours minimum to get a first successful build — plan for this
     to be a stretch goal, not a guaranteed 48-hour deliverable.

3. Progressive Web App only (no APK at all)
   - Since index.html is already a installable PWA (manifest.json + sw.js
     are in this repo), a phone can "Add to Home Screen" and get an
     app-like icon without any APK. This does NOT include the Python/
     Reticulum engine though — the PWA alone can't do mesh networking by
     itself; a bridge.py instance still needs to be running somewhere
     reachable (this device, or a laptop on the same hotspot).

Whichever path you take, once you have a signed centr.apk, just drop it
in this folder with that exact filename and /download/apk will start
serving it automatically — no code changes needed.

-------------------------------------------------------------------------

WINDOWS: centr_windows.exe (for a Windows PC with NO Python installed)

Same idea, different platform. A Windows laptop that has zero Python and
zero internet can't run `pip install` no matter what wheels you hand it,
because there's no Python to run pip with in the first place. The fix is
to freeze the whole app (Python interpreter + Flask + Reticulum + your
code) into one self-contained .exe using PyInstaller, built AHEAD OF TIME
on a Windows machine that still has internet.

Steps (run once, tonight, before you go offline):
  1. On any Windows machine with internet, from this project folder, run:
       .\build_windows_exe.ps1
  2. This installs PyInstaller, freezes bridge.py into dist\centr_windows.exe,
     and copies it here as static\bin\centr_windows.exe.
  3. From then on, /download/exe on whichever machine has that file will
     serve it to anyone on the same hotspot — they download one .exe and
     double-click it. No Python, no pip, no installer, no admin rights.

Notes:
  - PyInstaller builds are OS-specific: you must build this ON Windows.
    Building on Linux/Mac produces a Linux/Mac binary, not a Windows exe.
  - It's also somewhat CPU-architecture specific (build on a 64-bit Windows
    machine for a 64-bit target, which is virtually all modern laptops).
  - The exe will trigger a Windows SmartScreen "unrecognized publisher"
    warning on first run since it isn't code-signed — click "More info" ->
    "Run anyway". This is normal for an unsigned hackathon build, not a
    sign anything is broken.
  - Same rule as the apk: once a real centr_windows.exe sits in this
    folder, /download/exe serves it automatically — no code changes needed.
