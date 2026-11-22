# ACR Mod Manager

Manage supported community stages for Assetto Corsa Rally without Stage Exporter or WRC Generations.

**[Download the Windows installer](https://github.com/Faviogames/ACR-Mod-Manager/releases/latest)** · **[Your records online!](https://acrsplits.online/)**

## Get started

1. Install and select your Assetto Corsa Rally folder.
2. Put each supported stage's complete `.pak` / `.utoc` / `.ucas` set in the mods folder.
3. Close ACR and click **Scan**. Scanning is manual.
4. Use **Enable / Disable** to apply changes immediately; disabled stages are kept outside the game packages folder.

The manager builds menu tables from your installed game's originals and the supported stages it finds. It preserves stage images and descriptions, keeps backups, and offers **Restore backup**. See Settings for the backup locations. No level packs or game originals are distributed here.

The catalogue covers 160 WRC Generations routes. Recognition does not mean every exported route has been driven or individually tested. Unknown third-party mods are marked **Not supported**; detected table conflicts identify the package. Arbitrary third-party compatibility is not guaranteed.

Windows x64, Microsoft Edge WebView2 Runtime and a compatible ACR installation are required. This release targets ACR build **26756580**. The installer bundles Python and .NET; Stage Exporter and its closed core are not required. The first table extraction requires Internet for retoc's SHA256-checked compression dependency. The installer is not code-signed.

English / Español are available in the app. Updates opens the official release page when a newer stable installer is available; run that installer with the app closed. User settings and manager data remain separate from application versions.

## Español

Instala, selecciona ACR, copia los tres archivos de cada tramo soportado y pulsa **Escanear** con el juego cerrado. Activar/desactivar aplica el cambio al momento. Los tramos desactivados y los respaldos se conservan. Los mods desconocidos se muestran como **No soportado**; esta versión no integra automáticamente cualquier mod externo.

## Mod authors

Use **Submit a mod** in the app for the request template. Contact **faviogames** on [Discord](https://discord.com/users/180799704412585984). Include the mod's version, download link, target game build, dependencies, whether it works alone, which menu tables it replaces, and permission to adapt its menu entries. Nothing is uploaded or sent automatically.

## Source and builds

This repository contains the manager engine, web interface, native host, installer and build scripts. The curated runtime catalogue `official_database.json` and tool binaries are supplied in the installer, not committed to Git. To rebuild, copy `official_database.json`, `python/`, and `bin/` from an installed release next to these sources, install the .NET 10 SDK, then run `powershell -ExecutionPolicy Bypass -File build_installer.ps1`. NuGet restores WebView2 from its official feed. Do not add your game files, local profiles, backups or private caches to Git.

Checks: `python/python.exe -m unittest test_content test_updates` and `node --test test_ui.cjs`. The installer also supports `--self-test <absolute-report-path>` for isolated extraction and persistence checks; this does not replace an in-game test.

Third-party notices are in [licenses](licenses/). Game names and trademarks belong to their respective owners. This project is independent of the game developers.
