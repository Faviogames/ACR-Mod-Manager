"""Bounded retention of verified menu backups and explicitly marked stale temporaries.

Call only with the profile lock held. Unrecognized data and level snapshots stay protected.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time

import wr_content_transaction as tx

DEFAULTS = dict(enabled=True, keep_backups=3, max_backup_mb=512, temp_max_age_hours=24, pinned_journals=[])
OWNER = 'acr-content-manager/1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def linked(path):
    return path.is_symlink() or bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) if os.name == 'nt' else path.is_symlink()


def tree(path, parent):
    if path.parent.resolve() != parent.resolve() or linked(path): raise ValueError('Unsafe cleanup directory')
    files = []
    for current, dirs, names in os.walk(path, followlinks=False):
        for name in dirs + names:
            item = Path(current)/name
            if linked(item): raise ValueError('Linked cleanup entry')
        files.extend(Path(current)/name for name in names)
    return files


def backup_info(manager, folder, policy):
    info = dict(path=str(folder), bytes=0, eligible=False, reason='unrecognized')
    if not re.fullmatch('[a-f0-9]{16}', folder.name): return info
    try:
        files = tree(folder, manager.state/'backups')
        info['bytes'] = sum(p.stat().st_size for p in files)
        journal = read(folder/'journal.json')
        if journal.get('status') != 'applied':
            info['reason'] = journal.get('status', 'unrecognized'); return info
        if folder.name in policy['pinned_journals'] or journal.get('pinned') or (folder/'KEEP').exists():
            info['reason'] = 'pinned'; return info
        if journal.get('owner') not in (None, OWNER): return info
        rows = journal.get('files')
        if not isinstance(rows, list) or not rows: return info
        expected = {folder/'journal.json'}
        has_installed = False
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or row.get('volume_snapshot'): info['reason']='level snapshot'; return info
            target = Path(row['target'])
            tx.checked_target(target, manager.roots)
            if target == manager.state/'installed.json': has_installed=True
            elif target.parent == manager.mods:
                if not re.fullmatch(r'pakchunk99-(?:WrcgTables|WrcgZZStageMenu(?:_\d+)?|SandoRegistry_2)_P\.(?:pak|utoc|ucas)', target.name): return info
            elif target.parent == manager.state/'catalog' and target.name.endswith('.stage.json'): pass
            else: return info
            for key in ('before', 'after'):
                if row.get(key) is not None and not re.fullmatch('[a-f0-9]{64}', row[key]): return info
            if row.get('before'):
                before = folder/'before'/str(index)
                if not before.is_file() or before.stat().st_size > tx.LARGE_ASSET: return info
                # Corrupt recent copies cannot displace the last usable recovery copies.
                if tx.sha(before) != row['before']: return info
                expected.add(before)
        if not has_installed or set(files) != expected: return info
        info.update(eligible=True, reason='menu backup', rows=rows, stamp={str(p):[p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ino] for p in files},
                    modified=(folder/'journal.json').stat().st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError): pass
    return info


def cleanup_locked(manager, *, dry_run=False, running=tx.game_running, now=None):
    policy = dict(DEFAULTS, **manager.config.get('cleanup', {}))
    if type(policy['enabled']) is not bool: raise ValueError('Invalid cleanup switch')
    for key in ('keep_backups', 'max_backup_mb', 'temp_max_age_hours'):
        if type(policy[key]) is not int or not 1 <= policy[key] <= 1048576: raise ValueError('Invalid cleanup limit')
    if not isinstance(policy['pinned_journals'], list): raise ValueError('Invalid pinned backup list')
    report = dict(enabled=bool(policy['enabled']), dry_run=dry_run, removed_backups=0, removed_temporaries=0,
                  removed_logical_bytes=0, planned=[], protected=[], warnings=[])
    if not policy['enabled'] or running(): report['deferred']='disabled or game running'; return report
    now = time.time() if now is None else now
    backup_root = manager.state/'backups'
    if linked(manager.state) or (backup_root.exists() and linked(backup_root)):
        report['deferred']='linked state or backup root'; return report
    folders = list(backup_root.iterdir()) if backup_root.is_dir() else []
    backups = [backup_info(manager, p, policy) for p in folders if p.is_dir()]
    if any(b['reason'] in ('preparing','prepared','applying','unrecognized') for b in backups):
        report['warnings'].append('Unrecognized, corrupt or pending backup; recovery data retained')
        report['deferred']='unrecognized or pending recovery'; return report
    eligible = sorted((b for b in backups if b['eligible']), key=lambda b:b['modified'], reverse=True)
    protected = eligible[:policy['keep_backups']]
    report['protected'] = [b['path'] for b in protected] + [b['path'] for b in backups if not b['eligible']]
    candidates = eligible[policy['keep_backups']:]
    for info in reversed(candidates):
        path = Path(info['path'])
        if running(): report['deferred']='game opened'; break
        files = tree(path, backup_root)
        stamp = {str(p):[p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ino] for p in files}
        if stamp != info['stamp']: report['warnings'].append('Backup changed; kept '+path.name); continue
        if any(tx.sha(path/'before'/str(i)) != row['before'] for i,row in enumerate(info['rows']) if row.get('before')):
            report['warnings'].append('Backup integrity mismatch; kept '+path.name); continue
        report['planned'].append(str(path))
        if dry_run: continue
        # Fully checked absolute target, directly inside this profile's backup root.
        shutil.rmtree(path)
        report['removed_backups'] += 1; report['removed_logical_bytes'] += info['bytes']
    retained = sum(b['bytes'] for b in backups if Path(b['path']).exists())
    if retained > policy['max_backup_mb']*1024*1024:
        report['warnings'].append('Backup budget exceeded; protected recovery data retained')
    temp_roots = [manager.state]
    if manager.config.get('native_cache'):
        native = Path(manager.config['native_cache']).resolve()
        stock = Path(manager.config.get('game_paks', manager.mods.parent)).resolve()
        if native.is_dir() and native not in temp_roots and not native.is_relative_to(stock) and not linked(native): temp_roots.append(native)
    for parent in temp_roots:
      if any(part.casefold()=='work' for part in parent.parts): continue
      for path in parent.iterdir():
        if not path.is_dir() or not re.fullmatch(r'(?:build|incoming|adopt|register|sando|catalog)-[a-z0-9_]{8}', path.name): continue
        try:
            files = tree(path, parent)
            marker = path/'.acr-manager-temp.json'
            if marker not in files: continue
            data = read(marker)
            if data.get('schema') != 'acr-manager-temp/1' or data.get('directory') != str(path.resolve()): continue
            if now - max(p.stat().st_mtime for p in [path,*files]) < policy['temp_max_age_hours']*3600: continue
            if type(data.get('pid')) is not int or tx.pid_alive(data['pid']): continue
            report['planned'].append(str(path))
            if dry_run: continue
            if running(): report['deferred']='game opened'; break
            size = sum(p.stat().st_size for p in files)
            tree(path, parent)
            shutil.rmtree(path)
            report['removed_temporaries'] += 1; report['removed_logical_bytes'] += size
        except (OSError, ValueError, TypeError, KeyError):
            report['warnings'].append('Temporary folder kept: '+path.name)
    if not dry_run: tx.save(manager.state/'cleanup-report.json', report)
    return report
