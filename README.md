# ACR Pak Manager

Manage supported community stages for Assetto Corsa Rally without Stage Exporter or WRC Generations.

**[Download the Windows installer](https://github.com/Faviogames/ACR-Mod-Manager/releases/latest)** Â· **[Your records online!](https://acrsplits.online/)**

[Roadmap](ROADMAP.md) â€” storage, compatibility and future improvements.

## Get started

1. Install and open ACR Pak Manager. Steam libraries are detected automatically; if necessary, select your Steam folder. Selecting the game folder remains an advanced fallback.
2. Put each supported stage's complete `.pak` / `.utoc` / `.ucas` set in the mods folder.
3. Close ACR and click **Scan**. Scanning is manual.
4. Use **Enable / Disable** to apply changes immediately; disabled stages are kept outside the game packages folder.

The manager builds menu tables from your installed game's originals and the supported stages it finds. It preserves stage images and descriptions, keeps backups, and offers **Restore backup**. See Settings for the backup locations. No level packs or game originals are distributed here.

The catalogue covers 160 WRC Generations routes. Recognition does not mean every exported route has been driven or individually tested. Chile BioBio 0.4.4 (forward + reverse) has an exact-release integration using the registry supplied with the mod. On first integration, keep its original registry triplet installed alongside its level files. The manager reads these locally; it does not redistribute the mod or its assets. Chile BioBio 0.4.4 (forward + reverse) has an exact-release integration using the registry supplied with the mod. On first integration, keep its original registry triplet installed alongside its level files. The manager reads these locally; it does not redistribute the mod or its assets. Unknown third-party mods are marked **Not supported**; detected table conflicts identify the package. Arbitrary third-party compatibility is not guaranteed.

Windows x64, Microsoft Edge WebView2 Runtime and a compatible ACR installation are required. This release targets ACR build **26756580**. The installer bundles Python and .NET; Stage Exporter and its closed core are not required. The first table extraction requires Internet for retoc's SHA256-checked compression dependency. The installer is not code-signed.

English / EspaÃ±ol are available in the app. Updates opens the official release page when a newer stable installer is available; run that installer with the app closed. User settings and manager data remain separate from application versions.

## EspaÃ±ol

Instala y abre ACR Pak Manager: detecta ACR en las bibliotecas de Steam; si hace falta, indica tu carpeta de Steam. Copia los tres archivos de cada tramo soportado y pulsa **Escanear** con el juego cerrado. Activar/desactivar aplica el cambio al momento. Los tramos desactivados y los respaldos se conservan. Los mods desconocidos se muestran como **No soportado**; esta versiÃ³n no integra automÃ¡ticamente cualquier mod externo.


## Reviewed external mods

- **Chile BioBio 0.4.4 â€” Sando Rally:** forward and reverse managed together. First integration needs its original registry triplet installed alongside the level files.
- **ThiÃ©rache S1 3.3 â€” Oxmod:** exact-release integration, including its original logo/background and custom level paths. For manual addition, select the extracted `~mods` folder while keeping `menu/S1_seule/` beside it in the original extracted layout. Scan also recognizes the exact reviewed level and standalone registry if already installed. Combined registries that also register Chemin des Ã‰rables are deliberately not substituted automatically: those stages have not been reviewed.

These integrations read the user's own files. No third-party levels, images or original registry tables are redistributed. A mod author's new release is not automatically approved when its hashes change.

The interface now has a larger logo, cyan PAK lettering and an adapted **MOD ACTIVE / IN GAME** insignia. The insignia requires a manual Scan and a valid, compatible enabled mod whose menu registration is verified.

## Storage and recovery

The installer no longer keeps a complete copy of itself as the launcher. The
stable launcher shares the native application file using a hard link when
supported. A clean 0.2.1 payload contains **312,787,265 bytes (about 298 MiB)**;
the download is **224,435,849 bytes (about 214 MiB)**. User data, WebView2 cache,
backups and a previous installed version are additional. Previous installations
are retained for recovery; unknown legacy files are not deleted automatically.
This is an installed-space saving, not a small network/bootstrap installer.

After a successful synchronization, cleanup keeps the latest three eligible menu
backups by default. The 512 MiB budget never overrides protected recovery data.
Level snapshots, pinned, unknown and unfinished journals stay protected. Only
marked, abandoned app temporaries older than 24 hours are eligible for cleanup.
Game files, user mods, disabled stages and exporter `work/` are excluded.
Configuration is in the `cleanup` object: `enabled`, `keep_backups`,
`max_backup_mb`, `temp_max_age_hours` and `pinned_journals`. There is no cleanup
editor in the interface yet; see Settings for the profile directory.

## Updated mods

Support is not a promise for every future release of a mod. Reviewed external
mods use exact sizes and SHA256 hashes; a changed release must be reviewed again
before its integration can be used. Official WRCG rebuilds may be recognized
through their known internal level identity and integrity checks, within the
supported menu/schema. Neither mechanism proves the level will run on a different
game build. Unknown packages are not silently merged or given trusted hashes.


## Reviewed external mods

- **Chile BioBio 0.4.4 â€” Sando Rally:** forward and reverse managed together. First integration needs its original registry triplet installed alongside the level files.
- **ThiÃ©rache S1 3.3 â€” Oxmod:** exact-release integration, including its original logo/background and custom level paths. For manual addition, select the extracted `~mods` folder while keeping `menu/S1_seule/` beside it in the original extracted layout. Scan also recognizes the exact reviewed level and standalone registry if already installed. Combined registries that also register Chemin des Ã‰rables are deliberately not substituted automatically: those stages have not been reviewed.

These integrations read the user's own files. No third-party levels, images or original registry tables are redistributed. A mod author's new release is not automatically approved when its hashes change.

The interface now has a larger logo, cyan PAK lettering and an adapted **MOD ACTIVE / IN GAME** insignia. The insignia requires a manual Scan and a valid, compatible enabled mod whose menu registration is verified.

## Storage and recovery

The installer no longer keeps a complete copy of itself as the launcher. The
stable launcher shares the native application file using a hard link when
supported. A clean 0.2.1 payload contains **312,787,265 bytes (about 298 MiB)**;
the download is **224,435,849 bytes (about 214 MiB)**. User data, WebView2 cache,
backups and a previous installed version are additional. Previous installations
are retained for recovery; unknown legacy files are not deleted automatically.
This is an installed-space saving, not a small network/bootstrap installer.

After a successful synchronization, cleanup keeps the latest three eligible menu
backups by default. The 512 MiB budget never overrides protected recovery data.
Level snapshots, pinned, unknown and unfinished journals stay protected. Only
marked, abandoned app temporaries older than 24 hours are eligible for cleanup.
Game files, user mods, disabled stages and exporter `work/` are excluded.
Configuration is in the `cleanup` object: `enabled`, `keep_backups`,
`max_backup_mb`, `temp_max_age_hours` and `pinned_journals`. There is no cleanup
editor in the interface yet; see Settings for the profile directory.

## Updated mods

Support is not a promise for every future release of a mod. Reviewed external
mods use exact sizes and SHA256 hashes; a changed release must be reviewed again
before its integration can be used. Official WRCG rebuilds may be recognized
through their known internal level identity and integrity checks, within the
supported menu/schema. Neither mechanism proves the level will run on a different
game build. Unknown packages are not silently merged or given trusted hashes.

## Mod authors

Use **Submit a mod** in the app for the request template. Contact **faviogames** on [Discord](https://discord.com/users/180799704412585984). Include the mod's version, download link, target game build, dependencies, whether it works alone, which menu tables it replaces, and permission to adapt its menu entries. Nothing is uploaded or sent automatically.

## Source and builds

This repository contains the manager engine, web interface, native host, installer and build scripts. The curated runtime catalogue `official_database.json` and tool binaries are supplied in the installer, not committed to Git. To rebuild, copy `official_database.json`, `python/`, and `bin/` from an installed release next to these sources, install the .NET 10 SDK, then run `powershell -ExecutionPolicy Bypass -File build_installer.ps1`. NuGet restores WebView2 from its official feed. Do not add your game files, local profiles, backups or private caches to Git.

Checks: `python/python.exe -m unittest test_content test_content_app test_manual_and_backups test_updates test_discovery_cleanup test_brand_assets test_reviewed_paths` and `node --test test_ui.cjs`. The installer also supports `--self-test <absolute-report-path>` for isolated extraction and persistence checks; this does not replace an in-game test.

Third-party notices are in [licenses](licenses/). Game names and trademarks belong to their respective owners. This project is independent of the game developers.
