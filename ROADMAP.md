# ACR Pak Manager — roadmap

Actualizado: 24 de noviembre de 2026. Peticiones del propietario pendientes de implementar. Esta actualización del roadmap no cambia la aplicación ni activa ninguna limpieza.

## 1. Instalador más ligero

- [ ] Sustituir el instalador completo que hoy queda como lanzador por un ejecutable pequeño. Mantener instalación por usuario, accesos directos y compatibilidad con las instalaciones existentes.
- [ ] Evitar conservar de forma permanente el paquete comprimido completo además de la aplicación extraída. Como referencia medida, la instalación actual ocupa unos 530 MB: unos 309 MB extraídos más 221 MB del instalador/lanzador.
- [ ] Revisar las dependencias .NET/Python y las herramientas incluidas para reducir duplicaciones sin añadir requisitos del exportador ni descargar componentes de fuentes sin verificar.
- [ ] Compactar la base de definiciones y compartir imágenes repetidas entre tramos/variantes. Conservar imágenes, descripciones, créditos e integridad de los datos. Seguir leyendo las tablas originales desde el juego instalado.
- [ ] Conservar la versión actual y una anterior comprobada para recuperación; retirar versiones e instaladores antiguos solo después de verificar la nueva instalación.

Comprobación antes de publicar: medir descarga, instalación y datos por separado; probar instalación limpia, actualización, fallo durante la actualización y recuperación conservando configuración y biblioteca. La reducción final se medirá, no se da por conseguida en este roadmap.

## 2. Respaldos, cachés y limpieza controlada

- [ ] Mostrar por separado espacio de aplicación, respaldos, catálogo, caché de interfaz y temporales. Distinguir tamaño lógico de espacio realmente liberable cuando existen enlaces duros a niveles.
- [ ] Limpiar temporales propios de operaciones terminadas y detectar restos de cierres forzados. Recuperar primero cualquier operación interrumpida; no limpiar durante Scan, instalación o restauración.
- [ ] Añadir límites configurables para respaldos. **Propuesta inicial a evaluar:** conservar los tres últimos respaldos correctos de tablas y un presupuesto de 512 MB para respaldos de menú/metadatos, retirando los más antiguos que sean prescindibles.
- [ ] Proteger siempre el último respaldo utilizable, los marcados para conservar y cualquier archivo necesario para un diario de recuperación o restauración. Si el presupuesto no puede respetarse sin perder esa protección, avisar en lugar de borrar lo protegido.
- [ ] Revisar y eliminar cachés de reconocimiento y menús donantes sin uso solo cuando ninguna instalación ni respaldo los necesite. Evitar duplicar imágenes y definiciones completas innecesariamente.
- [ ] Añadir una acción de limpieza con vista previa: qué se retirará, por qué y cuánto espacio se puede recuperar. Registrar la operación. La limpieza automática solo afectará a datos propios que ya se hayan demostrado prescindibles.
- [ ] Mantener que un Scan sin cambios no reconstruya las tablas ni genere otro respaldo. Un mod nuevo no debe provocar copias completas de los niveles de varios GB.

Fuera del alcance de la limpieza: paks del usuario, otros mods, tramos desactivados, archivos del juego, configuración y capturas de récords. No tocar `work/` del exportador. Las carpetas de desarrollo y pruebas no se confunden con datos de una instalación normal.

Comprobación antes de publicar: límites superados, respaldos protegidos, enlaces duros, fallo o cierre durante una operación y restauración después de limpiar. Confirmar que no cambia ningún archivo ajeno al gestor.

## 3. Detectar Steam y localizar ACR sin pedir la carpeta del juego

- [ ] Detectar automáticamente la instalación de Steam en Windows a partir de sus ubicaciones registradas.
- [ ] Leer `steamapps/libraryfolders.vdf` para localizar todas las bibliotecas del usuario, incluidas las de otros discos.
- [ ] Buscar el manifiesto de ACR por su AppID y resolver su directorio instalado; no depender únicamente de que la carpeta tenga un nombre concreto.
- [ ] Validar que la instalación encontrada contiene los archivos originales necesarios y comprobar su compatibilidad antes de usarla. Guardar la selección para los siguientes arranques.
- [ ] Si Steam no se detecta, pedir solamente su carpeta raíz y buscar desde ella sus bibliotecas y ACR. Si hay varias instalaciones válidas, ofrecerlas para elegir.
- [ ] Conservar la selección avanzada de la carpeta del juego como último recurso para instalaciones movidas, rutas personalizadas o casos no estándar. Dar un mensaje claro si Steam existe pero ACR no está instalado.
- [ ] Detectar que el juego se ha movido y permitir volver a localizarlo sin perder los datos del gestor. Todo este descubrimiento es local y de solo lectura; no requiere iniciar sesión en Steam.

La autodetección de Steam/juego no cambia la decisión del propietario sobre interacción: **Scan de mods sigue siendo manual**.

Comprobación antes de publicar: Steam en ruta habitual y personalizada; ACR en otra biblioteca/disco; varias bibliotecas; juego ausente o movido; rutas con espacios y caracteres Unicode. El flujo habitual no debe obligar a navegar hasta `acr/Content/Paks`.

## Estado del candidato 0.2.0 (fuentes, sin publicar)

Implementados en next/: lanzador nativo sin retener el instalador completo,
retencion de versiones tras inicio saludable, autodeteccion local de Steam y
limpieza protegida de respaldos/temporales tras sincronizacion correcta.
Logo y nuevo icono ACR incorporados. Scan de mods sigue siendo manual.

Verificacion: 40 pruebas Python (39 correctas y 1 fixture omitido), 3 pruebas
JavaScript, sintaxis C# sin errores. Steam detecto la instalacion real en D:.
La limpieza real solo se simulo: 2 respaldos candidatos, 3 protegidos, 0 borrados.
No se ha compilado ni publicado; falta validar instalacion limpia, actualizacion,
accesos directos y recuperacion con los ejecutables nuevos antes de lanzamiento.
Siguen pendientes: compactar base de definiciones, panel de espacio/limpieza,
y retirada de caches donantes sin uso. No se presume una reduccion final medida.

## Validacion para publicar 0.2.0

Host e instalador compilados. La autoprueba del instalador confirma extraccion
aislada, repeticion de instalacion y conservacion de datos. Motor iniciado desde
el host nuevo con perfil aislado e interfaz comprobada, sin Scan ni cambios al
juego. Las pruebas Python/JavaScript vuelven a pasar. La limpieza del perfil
real permanece en simulacion; no se han borrado respaldos reales en esta tarea.
Tamanos medidos: instalador 223096969 bytes, payload extraido 311202632 bytes.
No hay una nueva prueba en el juego ni se han probado todos los escenarios de
fallo de actualizacion; mantener recuperacion conservadora.

## Release 0.2.1

Includes reviewed Thierache 3.3 recognition, exact custom asset paths, distinct
location/image row references, larger branding and active-state insignia.
Thierache lifecycle/rollback passed in isolation and the owner confirmed it
worked in game. Game validation is scoped to that reviewed mod release/build.
The 0.2.0 draft was superseded before public release; original game assets and
third-party level packages remain excluded from publication.
