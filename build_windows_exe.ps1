$ErrorActionPreference = "Stop"

Write-Host "Installing build deps and app deps..."
pip install --upgrade pip
pip install pyinstaller
pip install -r requirements.txt

Write-Host ""
Write-Host "Staging a copy of the .py sources for bundler.py to hand out..."
# Fix #1: bundler.py builds the self-distribution zip by reading .py files
# off disk. Inside a --onefile frozen exe, the original .py files are NOT
# on disk anywhere near __file__ - only compiled bytecode is. So we stage
# a plain copy of the sources into a "pysrc" folder and ship that folder
# into the exe via --add-data; bundler.py's _source_root() looks for it
# at sys._MEIPASS/pysrc at runtime.
New-Item -ItemType Directory -Force -Path "pysrc" | Out-Null
Copy-Item -Force config.py,database.py,auth.py,network.py,bundler.py,app.py,routes.py,main.py,requirements.txt "pysrc\"

Write-Host ""
Write-Host "Freezing main.py into a standalone Windows exe..."
pyinstaller --clean --onefile --name centr_windows `
  --collect-submodules RNS `
  --collect-data RNS `
  --collect-submodules cryptography `
  --collect-data cryptography `
  --hidden-import RNS.Interfaces.Interface `
  --hidden-import RNS.Interfaces.TCPInterface `
  --hidden-import RNS.Interfaces.LocalInterface `
  --hidden-import RNS.Interfaces.AutoInterface `
  --hidden-import RNS.Interfaces.UDPInterface `
  --hidden-import RNS.Interfaces.I2PInterface `
  --hidden-import RNS.Interfaces.RNodeInterface `
  --hidden-import RNS.Interfaces.RNodeMultiInterface `
  --hidden-import RNS.Interfaces.SerialInterface `
  --hidden-import RNS.Interfaces.KISSInterface `
  --hidden-import RNS.Interfaces.AX25KISSInterface `
  --hidden-import RNS.Interfaces.PipeInterface `
  --hidden-import RNS.Interfaces.BackboneInterface `
  --hidden-import RNS.Interfaces.WeaveInterface `
  --add-data "static;static" `
  --add-data "pysrc;pysrc" `
  main.py

Write-Host ""
Write-Host "Copying result into static/bin..."
New-Item -ItemType Directory -Force -Path "static\bin" | Out-Null
Copy-Item -Force "dist\centr_windows.exe" "static\bin\centr_windows.exe"

Write-Host ""
Write-Host "Done. static/bin/centr_windows.exe is ready for offline transfer."
