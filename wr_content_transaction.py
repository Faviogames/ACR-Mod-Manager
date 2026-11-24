"""Journaled publication, adapted from wr_maintenance.publish/rollback.

Backups survive process exits. Every replacement is staged before the first
installed file is changed; recovery never overwrites a subsequent installation.
"""
from contextlib import contextmanager
import csv
import ctypes
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile


def pid_alive(pid):
    if pid <= 0: return True
    if os.name != 'nt':
        try: os.kill(pid, 0); return True
        except ProcessLookupError: return False
        except PermissionError: return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle: return ctypes.get_last_error() != 87
    try: return kernel.WaitForSingleObject(handle, 0) == 258
    finally: kernel.CloseHandle(handle)


@contextmanager
def temporary_directory(parent, *, prefix):
    with tempfile.TemporaryDirectory(dir=parent, prefix=prefix) as folder:
        path = Path(folder).resolve()
        save(path/'.acr-manager-temp.json', dict(schema='acr-manager-temp/1', pid=os.getpid(), directory=str(path)))
        yield folder


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + os.urandom(5).hex() + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def game_running():
    # Same fail-closed process check as wr_mounts.game_running.
    result = subprocess.run(['tasklist.exe', '/FO', 'CSV', '/NH'], check=True,
                            capture_output=True, encoding='ascii', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return any(row and row[0].lower() in {'acr.exe', 'acr-win64-shipping.exe'}
               for row in csv.reader(result.stdout.splitlines()))


LARGE_ASSET = 64 * 1024 * 1024


def copy_asset(source, destination, *, allow_copy=True):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError as exc:
        if not allow_copy:
            raise RuntimeError("No se permite copiar un nivel completo para esta operación; revisa el disco de destino.") from exc
        shutil.copy2(source, destination)


@contextmanager
def profile_lock(profile):
    # Share the maintenance lock, so cooperating exporter and manager cannot deploy together.
    lock = Path(profile).parent / '.wrcg-maintenance.lock'
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if lock.is_symlink():
            raise RuntimeError('Bloqueo enlazado no válido: ' + str(lock))
        try:
            pid = int(lock.read_text(encoding='ascii'))
        except (ValueError, OSError):
            raise RuntimeError('Bloqueo no válido; conservar para revisión: ' + str(lock))
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        process = kernel.OpenProcess(0x100000, False, pid)
        if not process:
            alive = ctypes.GetLastError() != 87
        else:
            try:
                alive = kernel.WaitForSingleObject(ctypes.c_void_p(process), 0) == 258
            finally:
                kernel.CloseHandle(ctypes.c_void_p(process))
        if alive:
            raise RuntimeError('Otra operación usa el perfil: ' + str(lock))
        lock.unlink()
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(handle, str(os.getpid()).encode('ascii'))
        os.fsync(handle)
        yield
    finally:
        os.close(handle)
        lock.unlink(missing_ok=True)


def checked_target(value, roots):
    path = Path(value)
    if path.is_symlink() or not any(path.resolve().is_relative_to(r.resolve()) for r in roots):
        raise ValueError('Destino fuera de las carpetas gestionadas: ' + str(path))
    return path


def backup_path(journal, index, row, snapshots=None):
    if not row.get('volume_snapshot'):
        return journal.parent / 'before' / str(index)
    if snapshots is None or not re.fullmatch(r'[0-9a-f]{16}', journal.parent.name):
        raise ValueError('Ubicación de respaldo de nivel no válida')
    root=Path(snapshots).resolve()
    return checked_target(root/journal.parent.name/'before'/str(index), (root,))


def rollback(journal, roots, running=game_running, hash_file=sha, *, snapshots=None):
    if running():
        raise RuntimeError('Cierra ACR antes de restaurar')
    journal = Path(journal)
    state = json.loads(journal.read_text(encoding='utf-8'))
    if state['status'] == 'rolled_back':
        return
    for i, row in enumerate(state['files']):
        path = checked_target(row['target'], roots)
        digest = hash_file(path) if path.exists() else None
        if digest not in (row['before'], row['after']):
            raise RuntimeError('Una instalación posterior cambió ' + str(path))
        backup = backup_path(journal, i, row, snapshots)
        if row['before'] and hash_file(backup) != row['before']:
            raise ValueError('Respaldo dañado: ' + str(backup))
    # Restore through destination-volume staging so os.replace remains atomic per file.
    for i, row in enumerate(state['files']):
        if running():
            raise RuntimeError('ACR se abrió durante la recuperación; cierra el juego y repite')
        path = checked_target(row['target'], roots)
        if row['before']:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name('.' + path.name + '.restore-' + os.urandom(5).hex())
            copy_asset(backup_path(journal, i, row, snapshots), temporary, allow_copy=not row.get('volume_snapshot'))
            os.replace(temporary, path)
        elif path.exists():
            path.unlink()
    for row in state['files']:
        path = Path(row['target'])
        if (hash_file(path) if path.exists() else None) != row['before']:
            raise ValueError('La restauración no coincide: ' + str(path))
    state['status'] = 'rolled_back'
    save(journal, state)


def publish(changes, state_dir, roots, unchanged, running=game_running, replace=os.replace, hash_file=sha, *, snapshots=None):
    if running():
        raise RuntimeError('Cierra ACR antes de modificar el contenido')
    folder = Path(state_dir) / 'backups' / os.urandom(8).hex()
    folder.mkdir(parents=True)
    journal = folder / 'journal.json'
    state = {'owner': 'acr-content-manager/1', 'status': 'preparing', 'files': []}
    staged = []
    deletions={Path(target).resolve() for target,source in changes.items() if source is None}
    try:
        for i, (target, source) in enumerate(changes.items()):
            target = checked_target(target, roots)
            before = hash_file(target) if target.exists() else None
            after = hash_file(source) if source else None
            row=dict(target=str(target), before=before, after=after)
            state['files'].append(row)
            if before:
                if target.stat().st_size > LARGE_ASSET:
                    if snapshots is None:
                        raise RuntimeError('Los niveles grandes requieren una carpeta de respaldo en su mismo disco')
                    row['volume_snapshot']=True
                copy_asset(target, backup_path(journal, i, row, snapshots), allow_copy=not row.get('volume_snapshot'))
            if source:
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name('.' + target.name + '.new-' + os.urandom(5).hex())
                staged.append((temp, target))
                moving_level=Path(source).resolve() in deletions and Path(source).stat().st_size > LARGE_ASSET
                copy_asset(source, temp, allow_copy=not moving_level)
                if hash_file(temp) != after:
                    raise ValueError('La copia preparada no coincide: ' + str(target))
        state['status'] = 'prepared'
        save(journal, state)
        if running() or not unchanged():
            raise RuntimeError('El juego se abrió o el contenido cambió durante la preparación')
        state['status'] = 'applying'
        save(journal, state)
        try:
            for temp, target in staged:
                if running():
                    raise RuntimeError('ACR se abrió antes de terminar la instalación')
                replace(temp, target)
            for row in state['files']:
                if row['after'] is None:
                    if running():
                        raise RuntimeError('ACR se abrió durante el cambio de estado')
                    Path(row['target']).unlink(missing_ok=True)
            for row in state['files']:
                path = Path(row['target'])
                if (hash_file(path) if path.exists() else None) != row['after']:
                    raise ValueError('Verificación instalada fallida: ' + str(path))
            state['status'] = 'applied'
            save(journal, state)
        except BaseException:
            rollback(journal, roots, running, hash_file, snapshots=snapshots)
            raise
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
    return journal


def recover_pending(state_dir, roots, running=game_running, *, snapshots=None):
    for journal in sorted((Path(state_dir) / 'backups').glob('*/journal.json')):
        state = json.loads(journal.read_text(encoding='utf-8'))
        if state['status'] in ('prepared', 'applying'):
            rollback(journal, roots, running, snapshots=snapshots)
