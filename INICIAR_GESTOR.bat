@echo off
if exist "%~dp0local\viewer.json" (
    start "" "%~dp0desktop-bin\ACR Pak Manager.exe" --config "%~dp0local\viewer.json" %*
) else (
    start "" "%~dp0desktop-bin\ACR Pak Manager.exe" %*
)
