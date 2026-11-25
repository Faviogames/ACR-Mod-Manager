@echo off
cd /d "%~dp0"
if exist "%~dp0data\manager.json" (
 start "" "%~dp0desktop-bin\ACR Pak Manager.exe" --config "%~dp0data\manager.json" %*
) else (
 start "" "%~dp0desktop-bin\ACR Pak Manager.exe" %*
)
