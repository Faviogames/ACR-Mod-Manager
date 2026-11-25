"""Independent ACR content-manager CLI and shared engine (stdlib + retoc/UaTool).

Use `python wr_content.py --config manager.json --help`. No WRCG or frozen
tools module is needed, even when generating the per-stage manifests.
"""
import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile

import wr_content_transaction as tx
from wr_content_imports import remap_row
from wr_content_tools import ASSET_EXTS, MAIN, TABLES, Tools, asset_path
from wr_menu_tables import (_rows, _row_map, _ownership, _by_table, _field, _references,
                            merge_menu_tables)

REVISION = 6
NAME = 'pakchunk99-WrcgTables_P'
EXTS = ('.pak', '.utoc', '.ucas')
SCHEMA = 'stage-content/1'
MAX_MANIFEST = 64*1024*1024


def read(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).is_file() else default


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inventory_stamp(folder):
    return {str(p.resolve()): [p.stat().st_size, p.stat().st_mtime_ns] for p in sorted(Path(folder).rglob('*'))
            if p.is_file() and (p.suffix.lower() in EXTS or p.name.endswith('.stage.json'))}


class Hashes:
    def __init__(self, state, progress):
        self.path = state/'hashes.json'
        self.cache = read(self.path, {})
        self.progress = progress

    def file(self, path):
        path = Path(path)
        stat = path.stat()
        key = f'{stat.st_dev}:{stat.st_ino}' if stat.st_ino else str(path.resolve()).casefold()
        stamp = [stat.st_size, stat.st_mtime_ns]
        previous = self.cache.get(key, {})
        if previous.get('stamp') == stamp:
            return previous['sha256']
        h = hashlib.sha256()
        done = 0
        self.progress(path.name, 0, stat.st_size)
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8*1024*1024), b''):
                h.update(block)
                done += len(block)
                self.progress(path.name, done, stat.st_size)
        after = path.stat()
        if stamp != [after.st_size, after.st_mtime_ns] or after.st_ino != stat.st_ino:
            raise RuntimeError('El archivo cambió mientras se verificaba: ' + str(path))
        value = h.hexdigest()
        self.cache[key] = dict(stamp=stamp, sha256=value)
        if stat.st_size > 64*1024*1024:
            self.save()
        return value

    def save(self):
        tx.save(self.path, self.cache)


def terminal_progress(name, done, total):
    percent = int(done*100/max(total, 1))
    # Callback signature is shared with the future standalone GUI progress bar.
    bar = '#'*(percent//5) + '-'*(20-percent//5)
    print(f'\rVerificando {name}: [{bar}] {percent:3d}% ({done}/{total} bytes)',
          end='\n' if done == total else '', flush=True)


class Manager:
    def __init__(self, config, log=print, progress=terminal_progress):
        self.config = config
        self.mods = Path(config['mods']).resolve()
        self.disabled = Path(config.get('disabled', self.mods.parent.parent/'StageContentDisabled')).resolve()
        self.state = Path(config['state']).resolve()
        self.roots = (self.mods, self.disabled, self.state)
        self.log = log
        self.tools = Tools(config, log)
        self.state.mkdir(parents=True, exist_ok=True)
        self.mods.mkdir(parents=True, exist_ok=True)
        if self.disabled.is_relative_to(self.mods.parent) or self.state.is_relative_to(self.mods):
            raise ValueError('Desactivados/estado deben estar fuera de Paks y ~mods, respectivamente')
        profile_parent=self.mods.parent.parent if self.mods.name.lower()=='~mods' else self.mods.parent
        self.snapshots=profile_parent/'StageContentManagerBackups'/digest(str(self.mods).casefold())[:24]
        if self.snapshots.resolve().is_relative_to(self.tools.stock) or not self.snapshots.resolve().is_relative_to(profile_parent):
            raise ValueError('Los respaldos de niveles deben estar fuera de Paks')
        self.hashes = Hashes(self.state, progress)

    def identity(self):
        stock = self.tools.stock
        catalogs = {p.name: self.hashes.file(p) for p in sorted(stock.glob('*.utoc'))
                    if p.name.lower() == 'global.utoc' or
                    re.fullmatch(r'pakchunk\d+(?:optional)?-Windows\.utoc', p.name, re.I)}
        if catalogs.get('global.utoc') != self.config['global_catalog_sha256']:
            raise ValueError('Build de ACR desconocida: se necesita una compatibilidad validada')
        if self.hashes.file(self.tools.mapping) != self.config['mapping_sha256']:
            raise ValueError('El mapa de clases no coincide con la compatibilidad declarada')
        return dict(schema=self.config['schema_id'], catalogs=catalogs,
                    mapping=self.config['mapping_sha256'])

    def load_manifest(self, path, identity, *, require_compatible=True, files_root=None):
        if path.is_symlink() or path.stat().st_size > MAX_MANIFEST:
            raise ValueError('Manifiesto demasiado grande o enlazado: ' + str(path))
        data = read(path)
        if data.get('schema') != SCHEMA or data.get('producer') not in ('StageExporter', 'SandoRallyReviewed'):
            raise ValueError('Manifiesto no reconocido: ' + str(path))
        if not re.fullmatch(r'[a-z0-9]+_[a-z0-9_]+', data.get('id', '')):
            raise ValueError('Identificador de autor/tramo inválido')
        if not isinstance(data.get('version'), str) or not data['version']:
            raise ValueError('Versión de tramo ausente')
        if require_compatible and identity['schema'] not in data.get('compatible_schemas', []):
            raise ValueError('Tramo incompatible con el juego actual: ' + data['id'])
        files = data.get('files', {})
        stem = path.name.removesuffix('.stage.json')
        if data.get('producer') == 'SandoRallyReviewed':
            from wr_content_sando import validate_reviewed
            known = validate_reviewed(data)
            valid_stem = stem == known['stem']
        else:
            valid_stem = bool(re.fullmatch(r'pakchunk99-Wrcg[A-Za-z0-9_]+_P', stem)) and stem != NAME
        if not valid_stem:
            raise ValueError('Nombre de paquete inválido')
        if set(files) != {stem+ext for ext in EXTS}:
            raise ValueError('El manifiesto no describe exactamente su conjunto pak/utoc/ucas')
        for name, record in files.items():
            file = (Path(files_root) if files_root is not None else path.parent)/name
            if file.is_symlink() or not file.is_file() or file.stat().st_size != record['size']:
                raise ValueError('Archivo ausente o tamaño incorrecto: ' + name)
            if self.hashes.file(file) != record['sha256']:
                raise ValueError('SHA256 incorrecto: ' + name)
        if data.get('penalty_seconds') not in (None, 20):
            raise ValueError('Regla de penalización no admitida')
        tables = data.get('tables', {})
        if not tables or any(MAIN+p not in TABLES for p in tables):
            raise ValueError('Tabla no admitida en el manifiesto')
        track = data.get('track')
        if track not in package_tracks(data) or set(package_tracks(data)) != set(_row_map(tables, 'DT_Tracks')):
            raise ValueError('El manifiesto no registra su tramo')
        for asset in tables.values():
            if len({r['Name'].casefold() for r in _rows(asset)}) != len(_rows(asset)):
                raise ValueError('Nombres de filas duplicados')
            if any(i.get('ObjectName') == 'UnknownExport' for i in asset.get('Imports', [])):
                raise ValueError('Importaciones sin resolver en el manifiesto')
        for relative, record in data.get('assets', {}).items():
            safe_asset(relative)
            raw = base64.b64decode(record['data'], validate=True)
            if len(raw) != record['size'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
                raise ValueError('Asset de menú dañado: ' + relative)
        if data.get('preview'):
            preview_bytes(data)
        return data

    def scan(self, identity, *, disabling=(), errors=None):
        result = []
        ids, tracks = set(), set()
        for folder in (self.mods, self.disabled):
            if not folder.exists():
                continue
            sidecars = list(folder.glob('*.stage.json'))
            own_names = {p.name for p in sidecars}
            cached = [p for p in (self.state/'catalog').glob('*.stage.json')
                      if p.name not in own_names and (folder/p.name.removesuffix('.stage.json')).with_suffix('.utoc').is_file()]
            for path in sorted(sidecars+cached):
                internal = path.parent != folder
                try:
                    data = self.load_manifest(path, identity, require_compatible=False, files_root=folder)
                    if folder == self.mods and data['id'] not in disabling and identity['schema'] not in data['compatible_schemas']:
                        raise ValueError('Tramo incompatible con el juego actual: ' + data['id'])
                    if data['id'].casefold() in ids or any(t.casefold() in tracks for t in package_tracks(data)):
                        raise ValueError('Colisión de identificador o nivel: ' + data['id'])
                except (ValueError, OSError) as exc:
                    if errors is None:
                        raise
                    errors.append((folder, path.name.removesuffix('.stage.json'), str(exc)))
                    continue
                ids.add(data['id'].casefold())
                tracks.update(t.casefold() for t in package_tracks(data))
                result.append(dict(path=path, folder=folder, internal=internal, data=data, active=folder == self.mods))
        known = {name for r in result if r['active'] for name in r['data']['files']}
        for path in self.mods.iterdir():
            if (path.is_file() and path.suffix in EXTS and path.stem.startswith('pakchunk99-Wrcg')
                    and not is_menu(path.stem) and path.name not in known):
                if errors is None:
                    raise ValueError('No se pudieron preparar los datos internos de: ' + path.name)
        return result

    def conflicts(self, records):
        stage_tocs = {str((r.get('folder', r['path'].parent)/name).resolve()).casefold()
                      for r in records for name in r['data']['files'] if name.endswith('.utoc')}
        # Include nested folders and foreign mods outside ~mods. Stock stays separate.
        roots = [self.mods]
        if self.mods.is_relative_to(self.tools.stock):
            roots = [self.tools.stock]
        from wr_content_sando import companion_paths
        reviewed_menus = companion_paths(self, records)
        for root in roots:
            for path in sorted(root.rglob('*.utoc')):
                if path.parent == self.tools.stock and (path.name == 'global.utoc' or
                        re.fullmatch(r'pakchunk\d+(?:optional)?-Windows\.utoc', path.name, re.I)):
                    continue
                if is_menu(path.stem) and path.parent == self.mods:
                    continue
                if path.resolve() in reviewed_menus:
                    continue
                files = self.tools.listing(path)
                clashes = [p for p in files if p in TABLES or Path(p).stem == 'DA_RacePenaltyDataFreePractice']
                if clashes:
                    raise ValueError('Conflicto de tablas: ' + str(path) + ': ' + ', '.join(clashes))
                # Even a declared level pak cannot secretly replace menu tables.
                if str(path.resolve()).casefold() in stage_tocs:
                    continue
            for path in sorted(root.rglob('*.pak')):
                if path.parent == self.tools.stock and re.fullmatch(r'(?:global|pakchunk\d+(?:optional)?-Windows)\.pak',path.name,re.I):
                    continue
                if path.with_suffix('.utoc').is_file():
                    continue
                # shortcut: legacy third-party .pak indexes are not parsed yet; block
                # unknown containers until a tested legacy directory reader is shared.
                raise ValueError('No se puede descartar conflicto en pak legacy: ' + str(path))

    def synchronize(self, *, output=None, toggle=None, incoming=None, tracks=None, deactivate=(), running=tx.game_running):
        if tracks is not None and output is None:
            raise ValueError('Seleccionar tramos solo está permitido para exportar tablas sin instalar')
        if incoming and toggle:
            raise ValueError('Instala o cambia el estado en operaciones separadas')
        with tx.profile_lock(self.mods), tx.temporary_directory(self.state,prefix='incoming-') as incoming_temp:
            tx.recover_pending(self.state, self.roots, running, snapshots=self.snapshots)
            identity = self.identity()
            from wr_content_presentation import snapshot, retain_installed
            previous_presentation=snapshot(self,identity)
            from wr_content_catalog import adopt_installed
            adopt_installed(self, identity)
            disabling = set(deactivate) | ({toggle[0]} if toggle and not toggle[1] else set())
            records = self.scan(identity, disabling=disabling)
            self.conflicts(records)
            before = (inventory_stamp(self.mods), inventory_stamp(self.disabled), self.stock_stamp())
            movement = {}
            source_stamp = None
            if incoming:
                incoming = Path(incoming).resolve()
                if incoming == self.mods or incoming == self.disabled or incoming.is_relative_to(self.mods):
                    raise ValueError('La carpeta de entrada debe estar fuera del perfil instalado')
                manifests = sorted(incoming.glob('*.stage.json'))
                internal_incoming=not manifests
                if not manifests:
                    from wr_content_catalog import prepare_incoming
                    manifests=prepare_incoming(self,incoming,identity,Path(incoming_temp))
                source_stamp = inventory_stamp(incoming)
                additions = []
                for path in manifests:
                    data = self.load_manifest(path, identity,files_root=incoming)
                    if any(r['data']['id'].casefold() == data['id'].casefold() or
                           set(t.casefold() for t in package_tracks(r['data'])) & set(t.casefold() for t in package_tracks(data)) for r in additions):
                        raise ValueError('Tramos duplicados en la carpeta de entrada')
                    for name in data['files']:
                        if name.endswith('.utoc'):
                            owned = self.tools.listing(incoming/name)
                            if any(p in TABLES or Path(p).stem == 'DA_RacePenaltyDataFreePractice' for p in owned):
                                raise ValueError('El pak de nivel también contiene tablas: ' + name)
                            from wr_content_reviewed import level_paths
                            if any(path not in owned for path in level_paths(data)):
                                raise ValueError('El pak no contiene su nivel declarado')
                    previous = next((r for r in records if r['data']['id'] == data['id']), None)
                    if previous and previous['active'] and previous['data'] == data:
                        continue
                    if previous:
                        for name in record_files(previous):
                            movement[previous.get('folder', previous['path'].parent)/name] = None
                        records.remove(previous)
                    if any(set(t.casefold() for t in package_tracks(r['data'])) & set(t.casefold() for t in package_tracks(data)) for r in records):
                        raise ValueError('Otro autor ya registra ese nivel: ' + data['track'])
                    for name in [*data['files']]+([] if internal_incoming else [path.name]):
                        destination = self.mods/name
                        if destination.exists() and destination not in movement:
                            raise FileExistsError('Paquete no gestionado: ' + str(destination))
                        movement[destination] = incoming/name
                    additions.append(dict(path=path,folder=incoming,internal=internal_incoming,data=data,active=True))
                records.extend(additions)
            toggles = [(key, False) for key in deactivate] + ([toggle] if toggle else [])
            for target, active in toggles:
                row = next((r for r in records if r['data']['id'] == target), None)
                if row is None:
                    if toggle and target == toggle[0]:
                        raise ValueError('Tramo no encontrado: ' + target)
                    continue
                if row['active'] != active:
                    if active:
                        self.load_manifest(row['path'], identity, files_root=row.get('folder'))
                    destination = self.mods if active else self.disabled
                    for name in record_files(row):
                        src, dst = row.get('folder', row['path'].parent)/name, destination/name
                        if dst.exists():
                            raise FileExistsError(dst)
                        movement[dst] = src
                        movement[src] = None
                    row['active'] = active
                    row['folder'] = destination
            active = sorted((r for r in records if r['active']), key=lambda r: r['data']['id'])
            if tracks is not None:
                tracks = set(tracks)
                active = [r for r in active if set(package_tracks(r['data'])) & tracks]
                missing = tracks - {t for r in active for t in package_tracks(r['data'])}
                if missing:
                    raise ValueError('Faltan manifiestos instalados para: ' + ', '.join(sorted(missing)))
            signature = digest(dict(revision=REVISION, game=identity,
                                    physics=tx.sha(Path(__file__).resolve().parent/'physics_recipe.json'),
                                    manifests=[r['data'] for r in active]))
            installed = read(self.state/'installed.json', {})
            if (not movement and not output and installed.get('signature') == signature and
                    all((self.mods/name).is_file() and self.hashes.file(self.mods/name) == value
                        for name, value in installed.get('files', {}).items()) and installed.get('files')):
                self.hashes.save()
                self.cleanup(running=running)
                self.log('Sin cambios: no se reconstruyen tablas')
                return {'changed': False, 'stages': [r['data']['id'] for r in active]}
            retain_installed(self,active,previous_presentation)
            signature = digest(dict(revision=REVISION, game=identity,
                                    physics=tx.sha(Path(__file__).resolve().parent/'physics_recipe.json'),
                                    manifests=[r['data'] for r in active]))
            if not output and running():
                self.hashes.save()
                raise RuntimeError('Actualización pendiente: cierra ACR y vuelve a sincronizar')
            with tx.temporary_directory(self.state, prefix='build-') as temp:
                scratch = Path(temp)
                native = scratch/'native'
                baseline, penalty = self.tools.extract_stock(native, scratch)
                merged = deepcopy(baseline)
                assets = {}
                for row in active:
                    data = row['data']
                    if any(relative not in merged for relative in data['tables']):
                        raise ValueError('El juego actual no contiene todas las tablas que necesita este tramo')
                    check_collisions(merged, data['tables'])
                    merged, _ = merge_menu_tables(merged, data['tables'], package_tracks(data))
                    for relative, record in data.get('assets', {}).items():
                        if relative in assets and assets[relative] != record:
                            raise ValueError('Colisión de imagen de menú: ' + relative)
                        assets[relative] = record
                validate_references(merged)
                legacy = scratch/'legacy'
                self.log('Generando tablas para ' + str(len(active)) + ' tramos activos…')
                for relative, asset in merged.items():
                    self.tools.write(asset, legacy/MAIN/relative, scratch)
                penalty_json = self.tools.dump(penalty, scratch)
                if any(r['data'].get('penalty_seconds') for r in active):
                    apply_penalty(penalty_json)
                self.tools.write(penalty_json, legacy/penalty.relative_to(native), scratch)
                for relative, record in assets.items():
                    path = legacy/safe_asset(relative)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(base64.b64decode(record['data'], validate=True))
                if any(r['data'].get('producer') == 'StageExporter' for r in active):
                    from wr_content_physics import build_shared
                    build_shared(self,legacy,scratch)
                package = scratch/'package'
                self.tools.pack(legacy, package, NAME)
                files = {NAME+ext: tx.sha(package/(NAME+ext)) for ext in EXTS}
                if before != (inventory_stamp(self.mods), inventory_stamp(self.disabled), self.stock_stamp()):
                    raise RuntimeError('El contenido cambió durante la generación; no se instala nada')
                if output:
                    destination = Path(output)
                    if destination.exists():
                        raise FileExistsError('Elige una carpeta de salida nueva: ' + str(destination))
                    destination.mkdir(parents=True)
                    for name in files:
                        tx.copy_asset(package/name, destination/name)
                    tx.save(destination/'content-report.json', dict(signature=signature, game=identity,
                            stages=[r['data']['id'] for r in active], files=files))
                    self.hashes.save()
                    return {'changed': True, 'output': str(destination), 'files': files}
                desired = dict(signature=signature, game=identity, files=files,
                               stages=[r['data']['id'] for r in active])
                tx.save(scratch/'installed.json', desired)
                changes = {self.mods/name: package/name for name in files}
                # Retire old tool-owned menu generations only, preserving them in the journal.
                for path in self.mods.iterdir():
                    if path.suffix in EXTS and is_menu(path.stem) and path.name not in files:
                        changes[path] = None
                from wr_content_sando import companion_paths
                for path in companion_paths(self, records):
                    changes[path] = None
                changes.update(movement)
                for record in records:
                    if record.get('internal') and record['path'].parent==Path(incoming_temp):
                        changes[self.state/'catalog'/record['path'].name]=record['path']
                for record in records:
                    if record.get('internal') and record.get('_presentation_changed'):
                        prepared=scratch/'presentation-records'/record['path'].name
                        tx.save(prepared,record['data'])
                        changes[self.state/'catalog'/record['path'].name]=prepared
                changes[self.state/'installed.json'] = scratch/'installed.json'
                unchanged = lambda: (before == (inventory_stamp(self.mods), inventory_stamp(self.disabled), self.stock_stamp())
                                     and (not incoming or source_stamp == inventory_stamp(incoming)))
                journal = tx.publish(changes, self.state, self.roots, unchanged, running, hash_file=self.hashes.file, snapshots=self.snapshots)
                self.hashes.save()
                self.cleanup(running=running)
                self.log('Tablas instaladas; respaldo: ' + str(journal))
                return dict(changed=True, journal=str(journal), **desired)

    def cleanup(self, *, running=tx.game_running):
        try:
            from wr_content_cleanup import cleanup_locked
            report = cleanup_locked(self, running=running)
            count = report['removed_backups'] + report['removed_temporaries']
            if count: self.log('Automatic cleanup: '+str(count)+' obsolete backup/temporary folders removed')
            for warning in report['warnings']: self.log('Cleanup: '+warning)
        except Exception as error:
            self.log('Cleanup deferred; installed mods are unchanged: '+str(error))

    def stock_stamp(self):
        return {p.name: [p.stat().st_size, p.stat().st_mtime_ns] for p in self.tools.stock.glob('*')
                if p.is_file() and p.suffix in ('.utoc', '.ucas', '.pak')}


def package_tracks(data):
    tracks = data.get('tracks', [data.get('track')])
    if not isinstance(tracks, list) or not tracks or any(not isinstance(t, str) or not re.fullmatch(r'[A-Za-z0-9_]+', t) for t in tracks) or len({t.casefold() for t in tracks}) != len(tracks):
        raise ValueError('Lista de tramos del paquete no válida')
    return tracks


def safe_asset(relative):
    value = asset_path(relative)
    from wr_content_reviewed import ui_packages
    approved = str(Path(value).with_suffix('')).replace('\\','/') in ui_packages()
    if (not value.startswith('acr/Content/Data/UITextures/') and not approved) or Path(value).suffix not in ASSET_EXTS:
        raise ValueError('Asset de menú no permitido: ' + value)
    return value


def record_files(record):
    return list(record['data']['files']) + ([] if record.get('internal') else [record['path'].name])


def is_menu(stem):
    return stem == NAME or bool(re.fullmatch(r'pakchunk99-WrcgZZStageMenu(?:_\d+)?_P', stem))


def check_collisions(old, incoming):
    for path, asset in incoming.items():
        base = old.get(path)
        if base is None:
            continue
        rows = {r['Name'].casefold(): r for r in _rows(base)}
        for row in _rows(asset):
            previous = rows.get(row['Name'].casefold())
            if previous is None:
                continue
            candidate = remap_row(row, asset, deepcopy(base))
            a, b = deepcopy(previous), candidate
            if Path(path).stem == 'DT_TracksLocations':
                # Countries are intentionally shared. Tracks/default are reconciled by the existing fusion.
                for r in (a, b):
                    r['Value'] = [v for v in r['Value'] if v['Name'] not in ('Tracks', 'DefaultVariant')]
            if a != b:
                raise ValueError('Colisión de fila: ' + path + ': ' + row['Name'])


def validate_references(tables):
    names = {Path(path).stem.removeprefix('DT_'): {r['Name'] for r in _rows(asset)}
             for path, asset in tables.items()}
    for path, asset in tables.items():
        for row in _rows(asset):
            for table, name in _references(row):
                if name not in ('None', '') and table in names and name not in names[table]:
                    raise ValueError(f'Referencia ausente en {path}/{row["Name"]}: {table}/{name}')


def apply_penalty(asset):
    # Same native-game rule as wr_penalty.edit_table; never a custom timer.
    exports = asset['Exports']
    policy = next(e for e in exports if 'PropsCollision' in e['ObjectName'])
    count = 0
    for entry in next(p for p in policy['Data'] if p['Name'] == 'EffectsMap')['Value']:
        index = entry[1]['Value']
        if not isinstance(index, int) or not 0 < index <= len(exports):
            raise ValueError('Referencia de penalización inválida')
        for prop in exports[index-1].get('Data') or []:
            if prop['Name'] == 'TimePenalty':
                prop['Value'] = 20.0
                if 'IsZero' in prop:
                    prop['IsZero'] = False
                count += 1
    if count != 2:
        raise ValueError('El esquema de penalización del juego ha cambiado')


def preview_bytes(data):
    record = data.get('preview')
    if not record:
        return None
    raw = base64.b64decode(record['data'], validate=True)
    if (len(raw) > 8*1024*1024 or len(raw) != record['size'] or
            hashlib.sha256(raw).hexdigest() != record['sha256'] or len(raw) < 33 or
            not raw.startswith(b'\x89PNG\r\n\x1a\n') or raw[12:16] != b'IHDR'):
        raise ValueError('Vista previa PNG dañada o demasiado grande')
    width, height = struct.unpack('>II', raw[16:24])
    if not width or not height or width > 8192 or height > 8192 or width*height > 16*1024*1024:
        raise ValueError('Dimensiones de vista previa no admitidas')
    return raw


def register(manager, *, legacy, pak, track, stage_id, version, built_with, penalty=False, preview=None, output_path=None):
    """Exporter-side producer; consumes built assets, never rebuilds a stage or unpickles caches."""
    legacy, pak = Path(legacy), Path(pak)
    identity = manager.identity()
    if built_with != identity['schema']:
        raise ValueError('No se puede certificar un pak de otra build sin migración validada')
    with tx.temporary_directory(manager.state, prefix='register-') as temp:
        scratch = Path(temp)
        tables = {}
        for relative in sorted(TABLES):
            if (legacy/relative).exists():
                tables[relative[len(MAIN):]] = manager.tools.dump(legacy/relative, scratch)
        owned = _ownership(tables, track)
        if track not in _row_map(tables, 'DT_Tracks'):
            raise ValueError('El menú construido no contiene ' + track)
        selected = {}
        for relative, asset in tables.items():
            name = Path(relative).stem
            keys = set(owned['locations'] if name.startswith('DT_TracksLocations') else owned.get(name, []))
            part = deepcopy(asset)
            part['Exports'][0]['Table']['Data'] = [r for r in _rows(asset) if r['Name'] in keys]
            if name == 'DT_TracksLocations':
                for row in _rows(part):
                    prop = _field(row, 'Tracks')
                    if prop:
                        prop['Value'] = [v for v in prop['Value'] if ('Tracks', track) in _references(v)]
            if _rows(part):
                selected[relative] = part
        assets = {}
        packages = set()
        def references(value, source):
            if isinstance(value, str) and value.startswith('/Game/Data/UITextures/'):
                packages.add(value.split('.')[0].replace('/Game/', 'acr/Content/', 1))
            elif isinstance(value, dict):
                index = value.get('Value')
                if 'ObjectPropertyData' in value.get('$type', '') and isinstance(index, int) and index < 0:
                    seen = set()
                    while index:
                        if index in seen or not 0 < -index <= len(source['Imports']):
                            raise ValueError('Importación de textura inválida')
                        seen.add(index)
                        imp = source['Imports'][-index-1]
                        references(imp['ObjectName'], source)
                        index = imp.get('OuterIndex', 0)
                for child in value.values():
                    references(child, source)
            elif isinstance(value, list):
                for child in value:
                    references(child, source)
        for asset in selected.values():
            references(_rows(asset), asset)
        native_packages = set()
        for toc in manager.tools.stock.glob('*.utoc'):
            if re.fullmatch(r'pakchunk\d+(?:optional)?-Windows\.utoc', toc.name, re.I):
                native_packages.update(manager.tools.listing(toc))
        for package in sorted(packages):
            if package+'.uasset' in native_packages:
                continue
            for ext in ASSET_EXTS:
                path = legacy/(package+ext)
                if path.is_file():
                    raw = path.read_bytes()
                    assets[path.relative_to(legacy).as_posix()] = dict(size=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(), data=base64.b64encode(raw).decode())
            if package+'.uasset' not in assets or package+'.uexp' not in assets:
                raise ValueError('Falta imagen propia del tramo: ' + package)
        stem = pak.stem
        files = {}
        for ext in EXTS:
            path = pak.with_suffix(ext)
            files[path.name] = dict(size=path.stat().st_size, sha256=manager.hashes.file(path))
        data = dict(schema=SCHEMA, producer='StageExporter', id=stage_id, version=version,
                    built_with=built_with, compatible_schemas=[identity['schema']], track=track,
                    files=files, tables=selected, assets=assets, penalty_seconds=20 if penalty else None)
        if preview is not None:
            raw = Path(preview).read_bytes()
            data['preview'] = dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                   data=base64.b64encode(raw).decode('ascii'))
            preview_bytes(data)
        path = Path(output_path) if output_path is not None else pak.with_name(stem+'.stage.json')
        if path.exists():
            raise FileExistsError('El manifiesto ya existe: ' + str(path))
        if len(json.dumps(data).encode('utf-8')) > MAX_MANIFEST:
            raise ValueError('Las aportaciones exceden el límite del manifiesto')
        tx.save(path, data)
        try:
            manager.load_manifest(path, identity, files_root=pak.parent)
        except BaseException:
            path.unlink()
            raise
        manager.hashes.save()
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description='Gestor independiente de contenido ACR')
    parser.add_argument('--config', required=True, type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('scan')
    sync = sub.add_parser('sync')
    sync.add_argument('--output', type=Path, help='Generar sin instalar, en una carpeta nueva')
    for action in ('enable', 'disable'):
        sub.add_parser(action).add_argument('id')
    sub.add_parser('install').add_argument('source', type=Path)
    sub.add_parser('rollback').add_argument('journal', type=Path)
    reg = sub.add_parser('register')
    for option in ('legacy', 'pak', 'track', 'id', 'version', 'built-with'):
        reg.add_argument('--'+option, required=True)
    reg.add_argument('--crowd-penalty', action='store_true')
    reg.add_argument('--preview', type=Path)
    args = parser.parse_args(argv)
    manager = Manager(read(args.config))
    if args.command == 'register':
        print(register(manager, legacy=args.legacy, pak=args.pak, track=args.track,
                       stage_id=args.id, version=args.version, built_with=args.built_with,
                       penalty=args.crowd_penalty, preview=args.preview))
    elif args.command == 'scan':
        identity = manager.identity()
        for row in manager.scan(identity):
            print(row['data']['id'], row['data']['version'], 'activo' if row['active'] else 'desactivado')
        manager.hashes.save()
    elif args.command == 'rollback':
        with tx.profile_lock(manager.mods):
            journal = args.journal.resolve()
            if not journal.is_relative_to(manager.state/'backups'):
                raise ValueError('El respaldo no pertenece a este gestor')
            tx.rollback(journal, manager.roots, snapshots=manager.snapshots)
    else:
        print(json.dumps(manager.synchronize(output=getattr(args, 'output', None),
                         incoming=args.source if args.command == 'install' else None,
                         toggle=(args.id, args.command == 'enable') if args.command in ('enable', 'disable') else None),
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, StopIteration) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
