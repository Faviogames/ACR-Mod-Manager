ACR Pak Manager 0.2.2 — Portugal artwork and presentation preservation

- Refreshed official catalogue with current authored stage Card/Background textures, Portugal country artwork and description. Removed the fixed three-stage preview restriction.
- Refresh cached definitions when their presentation revision changes.
- Preserve real user changes to text, image selection and authored texture pixels while reading native tables fresh from the installed game.
- Correct migration of old HafrenSouth placeholder image references and generic WRCG descriptions previously mistaken for custom user edits. Comparison ignores serialization-only property flags.
- Preserve remembered custom presentation when disabling/re-enabling a stage.
- Save worker startup errors locally for diagnosis. Manual Scan remains required.

Close the manager, run ACR-Mod-Manager-Setup.exe and click Scan with ACR closed.
No stage re-export is needed. Existing menu backups remain available.

Validation: 52 Python tests passed (1 optional fixture skipped), plus 4 JavaScript tests; real-data isolated Portugal fresh install, preservation after adding Ngema, and export-only reproduction of the owner's exact bad cached image references. All eight Portugal stage image references point to their own textures after migration. No new in-game visual validation of this fix is claimed.

The standalone manager does not require Stage Exporter or WRCG. Developer catalogue regeneration uses authored inputs and an isolated private exporter worker; that worker, game originals and third-party level packages are not distributed. Known third-party releases remain Chile BioBio 0.4.4 and Thierache S1 3.3. Unknown new mod versions require review.

Español: instala esta actualización y pulsa Scan con el juego cerrado para reparar las imágenes de los tramos de Portugal. Se mantienen las personalizaciones reales del menú; no necesitas reexportar los mapas. El instalador no está firmado. Requiere Windows x64, WebView2 y ACR build 26756580.
