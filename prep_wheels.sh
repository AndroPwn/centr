#!/usr/bin/env bash
# centr — run this ONCE, while this machine still has internet, before
# you go fully offline. It downloads the actual package files (not just
# installs them) into a "wheels" folder next to bridge.py.
#
# Every /download/bundle served by THIS machine from then on will include
# those wheels, so anyone who pulls the bundle from you over a hotspot
# with zero internet can still install and run centr.
#
# Run from the centr project folder:
#   bash prep_wheels.sh
set -e

echo "Downloading centr's Python packages for offline install..."
pip3 download -r requirements.txt -d wheels

echo ""
echo "Done. wheels/ now contains:"
ls wheels

echo ""
echo "IMPORTANT: these wheels were built for THIS machine's OS, CPU"
echo "architecture, and Python version. They will NOT work for Windows or"
echo "Android (Termux) devices unless this machine matches them. Run this"
echo "same script once on a machine of each platform you plan to hand the"
echo "app to, if your fleet is mixed."
echo ""
echo "From now on, http://127.0.0.1:5000/download/bundle from this machine"
echo "will include these wheels automatically - no code change, no restart"
echo "needed, bridge.py picks up the wheels/ folder at request time."
