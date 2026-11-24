"""Local WebView2 interface using the same loopback/token pattern as ACR MOD RECORDS."""
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit, parse_qs

from wr_content import Manager, read, preview_bytes, is_menu, EXTS
import wr_content_transaction as tx
from wr_menu_tables import _row_map, _field

ROOT = Path(__file__).resolve().parent


def text(field, default=''):
    return (field or {}).get('CultureInvariantString') or (field or {}).get('SourceString') or default


def stage_details(data):
    track = _row_map(data['tables'], 'DT_Tracks').get(data['track'], {})
    location = next(iter(_row_map(data['tables'], 'DT_TracksLocations').values()), {})
    country = text(_field(location, 'Name')).replace('[MOD] ', '')
    country = {'Spain': 'España', 'Greece': 'Grecia', 'Kenya': 'Kenia'}.get(country, country)
    return dict(id=data['id'], name=data.get('display_name') or text(_field(track, 'Name'), data['track']), country=country,
                description=text(_field(location, 'HistoryAndTrivia')),
                version=data['version'], build=data['built_with'], author='Comunidad' if data['track'].startswith('Wrcg') else data.get('author') or data['id'].split('_', 1)[0],
                size=sum(f['size'] for f in data['files'].values()), has_preview=bool(data.get('preview')),
                preview_hash=data.get('preview', {}).get('sha256', ''),
                preview_scope=data.get('preview', {}).get('kind', 'stage'),
                compatibility_scope=data.get('compatibility_scope','full'))


def unregistered_packages(folder, active, registered=None):
    known = set(registered) if registered is not None else {p.name.removesuffix('.stage.json') for p in folder.glob('*.stage.json')}
    groups = {}
    for path in folder.iterdir() if folder.exists() else ():
        if path.is_file() and path.suffix.lower() in EXTS and path.stem not in known and not is_menu(path.stem):
            groups.setdefault(path.stem, []).append(path)
    return [dict(id='unregistered:'+stem, name=stem, country='', description=
                 ('Esta versión del paquete no está en el catálogo interno. Actualiza el gestor para incorporar su definición oficial antes de activarlo.' if stem.startswith('pakchunk99-Wrcg') else 'Mod externo detectado. Todavía no está integrado en el gestor; sus tablas y compatibilidad requieren revisión.'),
                 active=active, valid=False, compatible=False, registration_required=True,
                 reason='Versión no catalogada' if stem.startswith('pakchunk99-Wrcg') else 'No soportado', external=not stem.startswith('pakchunk99-Wrcg'), size=sum(p.stat().st_size for p in files),
                 version='Sin registrar', build='Sin verificar', author='Sin identificar', has_preview=False)
            for stem, files in sorted(groups.items())]


class Engine:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.lock = threading.RLock()
        self.value = dict(app='ACR Pak Manager', busy=False, stages=[], logs=[], progress=None,
                          message='Leyendo tu biblioteca…', error=None, synced=False, revision=0,
                          language=read(self.config_path, {}).get('language', 'en'), scanned=False,
                          release=read(ROOT/'app_release.json'),updates=dict(status='idle'))
        self.previews = {}

    def check_updates(self):
        with self.lock:
            if self.value['updates']['status']=='checking':
                return
            self.update(updates=dict(status='checking'))
        def work():
            try:
                from wr_content_updates import latest
                result=latest(self.value['release'])
            except Exception:
                result=dict(status='unreachable')
            self.update(updates=result)
        threading.Thread(target=work,daemon=True).start()

    def set_language(self, language):
        if language not in ('en', 'es'):
            raise ValueError('Idioma no admitido')
        with self.lock:
            config=read(self.config_path)
            config['language']=language
            tx.save(self.config_path, config)
            self.update(language=language)
        return language

    def state(self):
        with self.lock:
            return deepcopy(self.value)

    def update(self, **values):
        with self.lock:
            self.value.update(values)
            self.value['revision'] += 1

    def log(self, message):
        with self.lock:
            self.value['logs'] = (self.value['logs'] + [message])[-60:]
            self.value['message'] = message
            self.value['revision'] += 1

    def progress(self, name, done, total):
        self.update(progress=dict(name=name, done=done, total=total), message='Verificando archivos…')

    def library(self, manager, issue=None):
        identity = manager.identity()
        from wr_content_catalog import adopt_installed
        adoption_error = None
        try:
            with tx.profile_lock(manager.mods):
                adopt_installed(manager, identity)
        except (ValueError, OSError, RuntimeError) as exc:
            adoption_error = str(exc)
        errors = []
        records = manager.scan(identity, errors=errors)
        installed = read(manager.state/'installed.json', {})
        menu_matches = bool(installed.get('files')) and all(
            (manager.mods/name).is_file() and manager.hashes.file(manager.mods/name)==digest
            for name,digest in installed.get('files',{}).items())
        other_menus = any(is_menu(p.stem) and p.name not in installed.get('files',{})
                          for p in manager.mods.glob('*.utoc'))
        rows, previews = [], {}
        for record in records:
            data=record['data']
            row=stage_details(data)
            ready=record['active'] and menu_matches and not other_menus and data['id'] in installed.get('stages',[])
            row.update(active=record['active'], valid=True, menu_ready=ready,
                       compatible=identity['schema'] in data['compatible_schemas'])
            if data.get('preview'):
                previews[data['id']]=preview_bytes(data)
            rows.append(row)
        known={r['path'].name.removesuffix('.stage.json') for r in records}
        problems={(folder,stem):reason for folder,stem,reason in errors}
        for folder,active in ((manager.mods,True),(manager.disabled,False)):
            for row in unregistered_packages(folder,active,registered=known):
                official=not row['external']
                row['reason']='Requiere revisión' if official else 'No soportado'
                row['description']=problems.get((folder,row['name']),adoption_error if official else None) or row['description']
                if issue and row['name'] in issue:
                    row['description']=issue
                    if issue.startswith('Conflicto de tablas:'):
                        row['reason']='Conflicto de tablas'
                row['menu_ready']=False
                rows.append(row)
        with self.lock:
            self.previews = previews
        self.update(stages=sorted(rows, key=lambda r: r['name'].casefold()), game=str(manager.tools.stock),
                    mods=str(manager.mods), backups=str(manager.state/'backups'),
                    library_issue=adoption_error, menu_ready_count=sum(r.get('menu_ready',False) for r in rows))

    def load_saved_library(self):
        config=read(self.config_path)
        mods=Path(config['mods'])
        disabled=Path(config.get('disabled',mods.parent.parent/'StageContentDisabled'))
        state=Path(config['state'])
        rows,previews=[],{}
        for path in (state/'catalog').glob('*.stage.json'):
            try:
                data=read(path)
                active=all((mods/name).is_file() for name in data['files'])
                if not active and not all((disabled/name).is_file() for name in data['files']):
                    continue
                row=stage_details(data)
                row.update(active=active,valid=True,compatible=True,menu_ready=False)
                if data.get('preview'):
                    previews[data['id']]=preview_bytes(data)
                rows.append(row)
            except (ValueError,KeyError,OSError,TypeError):
                continue
        with self.lock:
            self.previews=previews
        pending_recovery=any(read(path,{}).get('status') in ('prepared','applying')
                             for path in (state/'backups').glob('*/journal.json'))
        self.update(stages=sorted(rows,key=lambda row:row['name'].casefold()),scanned=False,synced=False,
                    game=config['game_paks'],mods=str(mods),backups=str(state/'backups'),menu_ready_count=0,
                    message='Pulsa Escanear para revisar tus mods',
                    error='Hay una recuperación pendiente. Pulsa Escanear con ACR cerrado antes de jugar.' if pending_recovery else None)

    def start(self, action, body=None):
        body = body or {}
        if action not in ('load', 'sync', 'enable', 'disable', 'install', 'restore'):
            raise ValueError('Acción no admitida')
        with self.lock:
            if self.value['busy']:
                raise RuntimeError('Espera a que termine la operación actual')
            self.update(busy=True, error=None, progress=None, message='Preparando contenido…')
        def work():
            manager = None
            try:
                if action=='load':
                    self.load_saved_library()
                    return
                self.update(scanned=True)
                manager = Manager(read(self.config_path), log=self.log, progress=self.progress)
                self.library(manager)
                if action == 'sync':
                    manager.synchronize()
                elif action in ('enable', 'disable'):
                    if not isinstance(body.get('id'), str):
                        raise ValueError('Selecciona un tramo válido')
                    manager.synchronize(toggle=(body['id'], action == 'enable'))
                elif action == 'install':
                    manager.synchronize(incoming=Path(body['path']))
                elif action == 'restore':
                    journal = Path(body['path']).resolve()
                    if not journal.is_relative_to(manager.state/'backups'):
                        raise ValueError('El respaldo no pertenece a este gestor')
                    with tx.profile_lock(manager.mods):
                        tx.rollback(journal, manager.roots, snapshots=manager.snapshots)
                self.library(manager)
                manager.hashes.save()
                self.update(synced=action != 'load', message='Biblioteca al día' if action != 'load' else 'Biblioteca cargada')
            except Exception as exc:
                self.log(str(exc))
                self.update(error=str(exc), synced=False, message='Requiere tu atención')
                if manager is not None:
                    try:
                        self.library(manager, issue=str(exc))
                    except Exception:
                        pass
            finally:
                self.update(busy=False, progress=None)
        threading.Thread(target=work, daemon=False).start()


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, engine):
        super().__init__(('127.0.0.1', 0), Handler)
        self.engine = engine
        self.token = os.urandom(24).hex()
        self.origin = f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, media='application/json; charset=utf-8'):
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        for key, value in {'Content-Type': media, 'Content-Length': str(len(raw)), 'Cache-Control': 'no-store',
                           'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                           'Content-Security-Policy': "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"}.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Host no permitido'})
        path = urlsplit(self.path).path
        if path.startswith('/api/'):
            if self.headers.get('X-App-Token') != self.server.token:
                return self.send(403, {'error': 'Sesión no autorizada'})
            if path == '/api/state':
                return self.send(200, self.server.engine.state())
            if path == '/api/preview':
                key = parse_qs(urlsplit(self.path).query).get('id', [''])[0]
                with self.server.engine.lock:
                    raw = self.server.engine.previews.get(key)
                return self.send(200, raw, 'image/png') if raw else self.send(404, {'error': 'Sin imagen'})
            return self.send(404, {'error': 'Ruta inexistente'})
        files = {'/': 'index.html', '/app.css': 'app.css', '/app.js': 'app.js', '/logo.svg': 'logo.svg', '/translations.json': 'translations.json', '/assets/acr-logo.jpg': 'assets/acr-logo.jpg', '/assets/app-icon.svg': 'assets/app-icon.svg', '/assets/app-icon.png': 'assets/app-icon.png', '/assets/app.ico': 'assets/app.ico'}
        if path not in files:
            return self.send(404, {'error': 'Ruta inexistente'})
        file = ROOT/'ui'/files[path]
        try:
            return self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        except OSError:
            return self.send(404, {'error': 'Recurso no disponible'})

    def do_POST(self):
        if (not self.allowed() or self.headers.get('Origin') != self.server.origin or
                self.headers.get('X-App-Token') != self.server.token):
            return self.send(403, {'error': 'Origen o sesión no permitidos'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                return self.send(413, {'error': 'Solicitud demasiado grande'})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('Se espera un objeto')
            path = urlsplit(self.path).path
            if path == '/api/updates':
                self.server.engine.check_updates()
                return self.send(202, {'ok': True})
            if path == '/api/language':
                return self.send(200, {'language': self.server.engine.set_language(body.get('language'))})
            if path == '/api/shutdown':
                if self.server.engine.state()['busy']:
                    return self.send(409, {'error': 'Espera a que termine antes de cerrar'})
                self.send(200, {'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path != '/api/action':
                return self.send(404, {'error': 'Acción inexistente'})
            self.server.engine.start(body.get('action'), body)
            self.send(202, {'ok': True})
        except (ValueError, UnicodeError, KeyError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.send(409, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--no-sync', action='store_true', help='Revisión de interfaz: cargar sin reconstruir al abrir')
    args = parser.parse_args()
    config = read(args.config)
    engine = Engine(args.config)
    server = Server(engine)
    runtime = Path(config['state'])/'ui-runtime.json'
    tx.save(runtime, dict(origin=server.origin, token=server.token))
    engine.start('load')
    engine.check_updates()
    try:
        server.serve_forever()
    finally:
        runtime.unlink(missing_ok=True)
        server.server_close()


if __name__ == '__main__':
    main()
