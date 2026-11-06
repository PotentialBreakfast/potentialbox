# Removes PotentialBox, its shortcuts and saved settings. Python 3.12 stays (remove it in Windows Settings > Apps if you like).
$dest = Join-Path $env:LOCALAPPDATA 'PotentialBox'
# close a running PotentialBox (it runs as pythonw.exe, so match on the command line)
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*potentialbox*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('Desktop')) 'PotentialBox.lnk') -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\PotentialBox.lnk') -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\PotentialBox Manual.lnk') -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $env:APPDATA 'PotentialBox') -ErrorAction SilentlyContinue
Set-Location $env:TEMP
Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
Write-Host "PotentialBox removed." -ForegroundColor Green
