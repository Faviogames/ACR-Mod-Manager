ACR Pak Manager 0.2.0

- New name, supplied logo and white/cyan ACR application icon.
- Automatic Steam library discovery; Steam folder selection and advanced game-folder fallback.
- Lower installed footprint: the launcher no longer retains the full setup payload.
- Protected menu-backup retention (3 by default; 512 MiB soft budget) and cleanup of marked abandoned temporaries.
- Keep the current installation and previous version for recovery; unknown legacy folders stay protected.
- Reviewed integration for Chile BioBio 0.4.4, forward and reverse, using the user's own original registry on first integration. No third-party level/assets are included.
- Manual Scan, preserved images/descriptions, English/Spanish and existing profiles retained.

Download **ACR-Mod-Manager-Setup.exe** below. The stable asset/repository name is
kept so existing ACR Mod Manager clients receive this update. SHA256SUMS.txt
verifies the installer. Close the manager before running setup.

Download: about 213 MiB. Clean extracted application: about 297 MiB, plus user
data/cache/backups and any previous retained version. This avoids the extra full
setup copy on disk; it is not a network installer and does not compact the
catalogue yet. The downloaded installer may still remain in Downloads.

Validated: compiled Windows x64 host/setup; isolated installer extraction,
repeat installation, data preservation and healthy-version retention; 40 Python tests passed, 1 optional
fixture skipped; 3 JavaScript tests; real Steam discovery; protected cleanup
dry-run. No new in-game run was performed for this release.

Requires Windows x64, WebView2 and ACR build 26756580. First table extraction
requires Internet. Installer is unsigned. No level packs or original game tables
are distributed. Future third-party mod versions require review if their files
change; arbitrary external mods are not automatically supported.

Español: nueva identidad ACR Pak Manager, detección de Steam y menor espacio de
instalación al evitar guardar el instalador completo como lanzador. Limpieza
automática protegida de respaldos/temporales. Conserva tus ajustes; cierra la app
antes de actualizar. Chile BioBio 0.4.4 usa su registro original en la primera
integración. Escanear sigue siendo manual. No garantiza versiones futuras de mods.
