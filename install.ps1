# PotentialBox installer - installs Python 3.12 (if needed), the app, and a desktop shortcut.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA 'PotentialBox'

function Say($t) { Write-Host "`n>> $t" -ForegroundColor Yellow }
function Find-Py {
    $c = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe")
    foreach ($p in $c) { if (Test-Path $p) { return $p } }
    return $null
}

Write-Host "==============================" -ForegroundColor Yellow
Write-Host "   POTENTIALBOX INSTALLER"       -ForegroundColor Yellow
Write-Host "==============================" -ForegroundColor Yellow

# 1. Python 3.12 (private copy, does not touch any other Python you have)
$py = Find-Py
if (-not $py) {
    Say "Downloading Python 3.12 (about 25 MB)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $exe = Join-Path $env:TEMP 'python-3.12.10-amd64.exe'
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $exe -UseBasicParsing
    Say "Installing Python 3.12 (takes a minute)..."
    Start-Process $exe -Wait -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_tcltk=1',
        'Include_test=0', 'Include_launcher=0', 'Shortcuts=0', 'AssociateFiles=0'
    $py = Find-Py
    if (-not $py) { throw "Python did not install. Run this installer again, or install Python 3.12 from python.org." }
}
Write-Host "Python: $py"

# 2. Copy the app
Say "Copying PotentialBox to $dest"
New-Item -ItemType Directory -Force $dest | Out-Null
# close a running PotentialBox (it runs as pythonw.exe, so match on the command line)
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*potentialbox*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
Remove-Item -Recurse -Force (Join-Path $dest 'potentialbox') -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force (Join-Path $src 'potentialbox') $dest
Copy-Item -Force (Join-Path $src 'README.txt') $dest
Copy-Item -Force (Join-Path $src 'uninstall.ps1') $dest
$manual = Join-Path $src 'PotentialBox-Manual.pdf'
if (Test-Path $manual) { Copy-Item -Force $manual $dest }

# 3. Private environment + audio/MIDI libraries
$venv = Join-Path $dest 'venv'
$vpy  = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    Say "Making a private Python environment..."
    & $py -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
}
Say "Installing audio + MIDI libraries (numpy, scipy, sounddevice with ASIO, mido, python-rtmidi)..."
& $vpy -m pip install --disable-pip-version-check --quiet --upgrade pip
& $vpy -m pip install --disable-pip-version-check --quiet --upgrade -r (Join-Path $src 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "Library install failed. Check your internet connection and run the installer again." }

# 4. Quick check: list ASIO outputs and MIDI inputs
Say "Checking audio and MIDI..."
$check = @'
import os
os.environ["SD_ENABLE_ASIO"] = "1"
import sounddevice as sd, mido
mido.set_backend("mido.backends.rtmidi")
apis = sd.query_hostapis()
asio = [d["name"] for d in sd.query_devices() if apis[d["hostapi"]]["name"] == "ASIO" and d["max_output_channels"] >= 2]
print("ASIO outputs :", ", ".join(asio) if asio else "none found (PotentialBox will use WASAPI; see README for ASIO)")
ins = mido.get_input_names()
print("MIDI inputs  :", ", ".join(ins) if ins else "none (plug in the BeatStep Pro)")
'@
$checkFile = Join-Path $env:TEMP 'potentialbox_check.py'
Set-Content -Path $checkFile -Value $check -Encoding ASCII
& $vpy $checkFile

# 5. Shortcuts (Desktop + Start menu)
Say "Adding PotentialBox shortcuts..."
$ws = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'))
foreach ($dir in $places) {
    $l = $ws.CreateShortcut((Join-Path $dir 'PotentialBox.lnk'))
    $l.TargetPath = Join-Path $venv 'Scripts\pythonw.exe'
    $l.Arguments = '-m potentialbox.app'
    $l.WorkingDirectory = $dest
    $l.IconLocation = Join-Path $dest 'potentialbox\potentialbox.ico'
    $l.Description = 'PotentialBox - BeatStep Pro groovebox'
    $l.Save()
}
$m = Join-Path $dest 'PotentialBox-Manual.pdf'
if (Test-Path $m) {
    $l = $ws.CreateShortcut((Join-Path (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs') 'PotentialBox Manual.lnk'))
    $l.TargetPath = $m
    $l.Save()
}

$ver = (Select-String -Path (Join-Path $dest 'potentialbox\app.py') -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
Write-Host "`nDONE! PotentialBox $ver is installed and on your Desktop. Starting it now..." -ForegroundColor Green
Start-Process (Join-Path $venv 'Scripts\pythonw.exe') -ArgumentList '-m potentialbox.app' -WorkingDirectory $dest
