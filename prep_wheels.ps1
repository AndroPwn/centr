# centr — run this ONCE, while this machine still has internet,
# before you go fully offline. It downloads the actual package files
# (not just installs them) into a "wheels" folder next to bridge.py.
#
# Every /download/bundle served by THIS machine from then on will include
# those wheels, so anyone who pulls the bundle from you over a hotspot
# with zero internet can still install and run centr.
#
# Run from the centr project folder:
#   .\prep_wheels.ps1

Write-Host "Downloading centr's Python packages for offline install..."
pip download -r requirements.txt -d wheels

Write-Host ""
Write-Host "Done. wheels/ now contains:"
Get-ChildItem wheels | ForEach-Object { Write-Host "  $($_.Name)" }
Write-Host ""
Write-Host "IMPORTANT: these wheels were built for THIS machine's OS, CPU"
Write-Host "architecture, and Python version. They'll work for other Windows"
Write-Host "laptops with a similar Python version, but will NOT work for"
Write-Host "Android (Termux) or Mac. Run this same script once on a machine"
Write-Host "of each platform you plan to hand the app to, if your fleet is mixed."
Write-Host ""
Write-Host "From now on, http://127.0.0.1:5000/download/bundle from this"
Write-Host "machine will include these wheels automatically - no code change,"
Write-Host "no restart needed, bridge.py picks up the wheels/ folder at request time."
