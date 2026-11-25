@echo off
cd /d "%~dp0"
start "" "%~dp0desktop-bin\ACR Pak Manager.exe" --config "%~dp0data\manager.json" --no-sync
