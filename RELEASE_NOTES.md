ACR Pak Manager 0.2.1

- New ACR Pak Manager identity, larger supplied logo, cyan PAK and R, and a new transparent MOD ACTIVE / IN GAME insignia. Removed Local library from the header.
- Automatic Steam library discovery; Steam-folder selection and advanced game-folder fallback.
- Lower installed footprint: setup is no longer retained as the launcher; same-volume native launcher hardlinks avoid a duplicate copy.
- Protected menu-backup retention (latest 3 by default, 512 MiB soft budget), marked stale-temporary cleanup and retention of a previous healthy app version. Unknown/unfinished/corrupt or pinned recovery data remains protected.
- Reviewed Chile BioBio 0.4.4 forward/reverse and Thiérache S1 3.3 integrations, using the player's original mod registries. Custom level paths and distinct location/image row keys are supported without widening asset permissions to arbitrary paths.
- Manual Scan, English/Spanish, existing profiles and original mod images/descriptions preserved. Future third-party mod updates still require review.

Download **ACR-Mod-Manager-Setup.exe** and close the manager before running it.
The repository and asset filenames remain stable for existing update checks.
The v0.2.0 draft was superseded before publication; this release includes the final Thierache and interface changes.

For Thiérache manual addition, keep the author's extracted layout intact and select its `~mods` folder; its `menu/S1_seule` registry must remain beside it. The combined registry for Chemin des Érables is not automatically adopted. No mod levels/assets are redistributed.

Validation: 43 Python tests passed, 1 optional real fixture skipped; 4 JavaScript tests. Isolated real-data Thierache installation, disable/re-enable, no-change detection and rollback passed; existing level files were unchanged. The owner confirmed Thierache worked in game. Clean extraction, repeat installation, profile preservation, previous healthy version retention and standalone Python/catalogue checks are covered by the installer self-test.

Requires Windows x64, WebView2 and supported ACR build 26756580. First table extraction requires Internet. Installer is unsigned. Application data/cache/backups and a previous retained version require additional storage; the downloaded setup can remain in Downloads. Database compaction and donor-cache pruning are not included.

Español: nueva imagen y distintivo de mods activos, detección de Steam, menor espacio instalado y limpieza protegida. Soporte revisado de Chile BioBio 0.4.4 y Thiérache S1 3.3; el propietario confirmó Thierache dentro del juego. Conserva los archivos extraídos del mod y sus menús originales para la primera integración. Escanear sigue siendo manual. Cierra el gestor antes de actualizar.
