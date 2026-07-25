# centr

Zero-infrastructure mesh messaging, groups, file transfer, and location
sharing — built on [Reticulum](https://reticulum.network/), for when the
internet and cell towers are down.

centr turns any phone or laptop into a node on a self-forming mesh
network. Messages hop device-to-device (Wi-Fi Direct, hotspot chains, or
LoRa) until they reach their destination, with no server, no SIM, and no
internet connection required anywhere along the path.

> **Before you lose internet access, run `prep_wheels.sh` (or
> `prep_wheels.ps1` on Windows) once on at least one device per platform
> (Windows / macOS / Linux / Android-Termux) you expect to hand this to.**
> Without this, `/download/bundle` still works, but the receiving device's
> `pip install` step needs internet it may not have during an actual
> blackout. See "Getting it onto another device with zero internet" below.

---

## Features

### Messaging
- **1:1 encrypted chat** over Reticulum's end-to-end encrypted links —
  intermediate hops only ever see opaque encrypted packets, never
  plaintext.
- **Store-and-forward delivery.** If no path to the recipient exists yet,
  a message is queued locally and automatically retried as new peers and
  routes appear — it doesn't need a live connection at send time.
- **Group chats** via shared group ID + symmetric key, distributed
  through an invite link. Any relaying device forwards the encrypted
  bytes without needing to be a group member itself.
- **Delivery status tracking** (queued → sent → delivered) and a local
  message history/inbox per conversation.

### File transfer
- Send **images, video, audio, and general files/documents** directly
  through a chat, using Reticulum's `Resource`/chunked-transfer APIs so
  large payloads survive slow or intermittent links.
- Broad file-type support out of the box: common image, video, audio,
  document (`docx`, `xlsx`, `pptx`, `pdf`, `odt`, ...), archive, and
  text/code formats are all recognized and handled.
- Configurable size limits per media type to keep transfers realistic on
  constrained links (Bluetooth LE / LoRa vs. Wi-Fi Direct).

### Location sharing
- Share your current location into a chat or group, viewable on a live
  map, so people can find each other without any mapping service or data
  connection.

### Built for blackouts
- **No internet, no cell network, no central server required** — the
  entire app runs peer-to-peer over Reticulum.
- **Partition-tolerant by design.** If the only relay between two people
  goes offline, messages queue silently and deliver automatically the
  moment a path reappears — verified in testing to recover within
  seconds of a relay coming back online.
- **Hotspot-chain relaying.** One phone's hotspot can carry traffic for
  the next device in the chain, extending reach hop by hop with nothing
  but phones people already have.
- **Opt-in relaying.** Devices only forward traffic for others once the
  owner explicitly turns on "help relay messages for others nearby" —
  never silently.
- **Self-distributing.** Any running instance can hand its own install
  bundle (`/download/bundle`) to a nearby device over the local
  hotspot/Wi-Fi — no app store or internet connection needed to spread
  the app itself.
- **One identity, one passcode per device.** Every install generates its
  own fresh Reticulum identity and a unique passcode on first boot — no
  central account system to depend on.

---

## How it works

Every device runs `bridge.py`, which does two jobs:

1. **Talks to the mesh** via Reticulum — announcing itself, discovering
   peers, and (optionally) relaying traffic for others when relay mode is
   turned on.
2. **Serves a local web UI/PWA** (the `static/` app) over Flask, so you
   drive the whole thing from a browser at `http://127.0.0.1:5000` —
   works the same on desktop or "Add to Home Screen" on mobile.

Devices connect to each other over whatever link is available —
Bluetooth/Wi-Fi Direct in range, a shared hotspot, a TCP link between
known IPs, or LoRa radio for longer distances — and Reticulum handles
routing and end-to-end encryption on top.

### Bluetooth, specifically

Today centr's config generation (`write_reticulum_config`) only writes
IP-based `TCPServerInterface` / `TCPClientInterface` entries. There are two
ways to get Bluetooth working, in order of effort:

- **Bluetooth PAN / tethering (works today, zero code changes).** Pair the
  two devices over Bluetooth and turn on Bluetooth tethering/PAN — the OS
  then exposes that link as a normal IP interface, so the existing TCP
  interface setup just works over it. Set `centr_CONNECT_TO` to the
  peer's PAN IP.
- **Native Bluetooth Interface (real fix, more work).** A custom
  Reticulum `Interface` subclass using `PyBluez` (Classic) or `bleak`
  (BLE) for devices that don't support PAN. The community project
  `torlando-tech/ble-reticulum` is a solid reference/starting point. Not
  implemented yet.

### Multi-hop / bridging two link types at once

`centr_CONNECT_TO` accepts a comma-separated list of `host:port` targets,
so a phone that's bridging a Bluetooth-PAN peer and a Wi-Fi-hotspot peer
at the same time (the "hotspot chain" scenario) can connect out to both
simultaneously, e.g.:

```bash
centr_CONNECT_TO="192.168.44.1:4242,192.168.43.1:4242" python main.py
```

Turn on relay mode (Settings tab) on the bridging device so it actually
forwards traffic between the two, not just for itself.

## Getting started

**Windows — prebuilt exe (nothing to install):**
`static/bin/centr_windows.exe` (also served at `/download/exe`) is a
PyInstaller `--onefile` build with Python, Reticulum, and all other
dependencies frozen inside it. Just run it — no Python or `pip install`
needed on that machine.

**Running from source (any platform):**
```bash
pip install -r requirements.txt
python main.py
```

Either way, on first run centr prints a one-time 6-digit device passcode
and starts the local web server. Open the printed address in a browser to
log in.

Useful environment variables:

| Variable | Purpose |
|---|---|
| `centr_HOME` | Where identity, database, and config live (default `~/.centr`) |
| `centr_NO_AUTH` | Set to `1` to skip the passcode login (local testing only) |
| `centr_LISTEN_PORT` | Port this device listens for other nodes on (default `4242`) |
| `centr_CONNECT_TO` | `host:port` of another device to join its network |

## Getting it onto another device with zero internet

Any device already running centr can hand the app itself to a new device
over a local hotspot connection — visit `/download/bundle` on the running
instance from the new device's browser (or `curl` it) to get a zip with
the full app and installer scripts for Termux (Android), macOS/Linux, and
Windows. Each new install generates its own identity and passcode, then
can pass the bundle on to the next device in turn. Binaries
(`centr_windows.exe`, `centr.apk`, `termux.apk`) that the source device
has on disk are automatically included in the same bundle under `bin/`,
so a device that only ever installed from source can still re-serve those
binaries to the next hop.

**Getting Termux itself, offline:** if the new Android device doesn't
have Termux installed and there's no internet, `/download/termux` on a
running instance serves a bundled Termux APK (from F-Droid/GitHub
releases — GPLv3, freely redistributable, unlike the deprecated Play
Store build) the same way `/download/apk` serves centr's own APK. See
`static/bin/PLACEHOLDER_README.txt` for how to place it.

**Honest caveat:** one device, somewhere, still needs to be prepped with
internet access before the blackout starts — to get centr itself, ideally
Termux too, and the dependency wheels for its platform (see the boxed
note near the top of this README). That's unavoidable, not a bug in the
zero-internet claim: everything *downstream* of that first prepped device
propagates with zero internet at every later hop.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entry point |
| `app.py` | Flask app setup |
| `routes.py` | HTTP/API endpoints (auth, messaging, groups, files, location) |
| `network.py` | Reticulum mesh networking layer |
| `auth.py` | Passcode-based device login |
| `database.py` | Local SQLite storage (messages, peers, groups, settings) |
| `bundler.py` | Builds the self-distributing install bundle |
| `config.py` | App paths, env vars, media-type/size settings |
| `static/` | Web UI (PWA) |
