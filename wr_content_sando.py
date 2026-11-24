import wr_content_transaction as tx
"""Reviewed, exact-release adapter. Uses the user's own installed registry only."""
from pathlib import Path
from copy import deepcopy
import base64
import hashlib

from wr_content import EXTS, read, inventory_stamp, is_menu
from wr_content_transaction import save
from wr_menu_tables import _ownership, _join_ownership, _rows, _row_map

ROOT=Path(__file__).resolve().parent


def catalogue():
    data=read(ROOT/'third_party_catalog.json',{})
    if data.get('schema')!='reviewed-packages/1':
        return {}
    return data.get('packages',{})


def validate_reviewed(data):
    known=catalogue().get(data.get('id'))
    if not known or any(data.get(key)!=known[key] for key in ('files','tracks','version','compatible_schemas','companion')):
        raise ValueError('Publicación externa no revisada; se necesita actualizar su compatibilidad')
    if data.get('track')!=known['tracks'][0]:
        raise ValueError('Tramo principal externo no válido')
    return known


def companion_paths(manager,records):
    """Only exact, reviewed registry triplets may be retired with a journal backup."""
    result=set()
    for row in records:
        data=row['data']
        if data.get('producer')!='SandoRallyReviewed':
            continue
        known=validate_reviewed(data)
        expected=known['companion']
        present=[manager.mods/name for name in expected if (manager.mods/name).exists()]
        if present and len(present)!=len(expected):
            raise ValueError('Registro externo incompleto; no se sustituye automáticamente')
        for path in present:
            info=expected[path.name]
            if path.is_symlink() or path.stat().st_size!=info['size'] or manager.hashes.file(path)!=info['sha256']:
                raise ValueError('El registro externo cambió; hay que revisar sus tablas antes de sustituirlo')
            result.add(path.resolve())
    return result


def adopt_installed(manager,identity):
    from wr_content_catalog import read_menu
    from wr_content import TABLES
    import tempfile
    for stage_id,known in catalogue().items():
        stem=known['stem']
        for folder in (manager.mods,manager.disabled):
            toc=folder/(stem+'.utoc')
            if not toc.is_file():
                continue
            cached=manager.state/'catalog'/(stem+'.stage.json')
            if cached.is_file():
                manager.load_manifest(cached,identity,files_root=folder)
                continue
            if known.get('adapter')=='explicit-paths/1':
                from wr_content_reviewed import adopt_one
                adopt_one(manager,folder,identity,stage_id,known)
                continue
            before=inventory_stamp(folder)
            if identity['schema'] not in known['compatible_schemas']:
                raise ValueError('Chile BioBio no es compatible con esta build')
            for name,info in known['files'].items():
                path=folder/name
                if path.is_symlink() or not path.is_file() or path.stat().st_size!=info['size'] or manager.hashes.file(path)!=info['sha256']:
                    raise ValueError('Versión de Chile BioBio sin revisar: '+name)
            contents=manager.tools.listing(toc)
            if any(p in TABLES for p in contents) or any('acr/Content/Levels/'+track+'.umap' not in contents for track in known['tracks']):
                raise ValueError('El contenido de Chile BioBio no coincide con la publicación revisada')
            data=dict(schema='stage-content/1',producer='SandoRallyReviewed',id=stage_id,
                      track=known['tracks'][0],tracks=known['tracks'],version=known['version'],
                      files=known['files'],compatible_schemas=known['compatible_schemas'],
                      built_with='ACR 26756580',companion=known['companion'],penalty_seconds=None,
                      display_name='Chile BioBio + Reverse',author='Sando Rally',
                      compatibility_scope='menu',catalog_origin='reviewed-sando-local/1',
                      credits=known['credits'],licence=known['licence'])
            companions=companion_paths(manager,[dict(data=data)])
            source=next((p for p in companions if p.suffix=='.utoc'),None)
            if source is None:
                raise ValueError('Primera integración de Chile: se necesita su registro original instalado')
            manager.log('Integrando Chile BioBio y Reverse desde tus archivos originales…')
            with tx.temporary_directory(manager.state,prefix='sando-') as temporary:
                scratch=Path(temporary)
                tables=read_menu(manager,source,scratch)
                owned=_join_ownership(*(_ownership(tables,t) for t in known['tracks']))
                selected={}
                for relative,asset in tables.items():
                    name=Path(relative).stem
                    keys=set(owned['locations'] if name.startswith('DT_TracksLocations') else owned.get(name,[]))
                    part=deepcopy(asset)
                    part['Exports'][0]['Table']['Data']=[r for r in _rows(asset) if r['Name'] in keys]
                    if _rows(part):selected[relative]=part
                if set(_row_map(selected,'DT_Tracks'))!=set(known['tracks']):
                    raise ValueError('El registro no contiene las dos direcciones de Chile')
                assets={}
                for path in (scratch/'acr/Content/Data/UITextures').rglob('*'):
                    if path.is_file():
                        raw=path.read_bytes()
                        assets[path.relative_to(scratch).as_posix()]=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode())
                data.update(tables=selected,assets=assets)
            preview=manager.mods/'files/data/ui/location_background.png'
            if preview.is_file() and preview.stat().st_size<=8*1024*1024:
                raw=preview.read_bytes()
                data['preview']=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode(),kind='location')
            if before!=inventory_stamp(folder):
                raise RuntimeError('Los archivos de Chile cambiaron durante la integración')
            save(cached,data)
            try:
                manager.load_manifest(cached,identity,files_root=folder)
            except BaseException:
                cached.unlink()
                raise
            manager.hashes.save()
