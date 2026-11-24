"""Local adoption of exact reviewed releases with explicit level and UI paths."""
from copy import deepcopy
from pathlib import Path
import base64
import hashlib
import shutil

import wr_content_transaction as tx
from wr_content import read, EXTS, MAIN, TABLES, inventory_stamp, validate_references
from wr_menu_tables import _rows, _row_map


def level_paths(data):
    if data.get('producer') == 'SandoRallyReviewed':
        from wr_content_sando import validate_reviewed
        known = validate_reviewed(data)
        if known.get('level_paths'):
            return known['level_paths']
    return ['acr/Content/Levels/'+t+'.umap' for t in data.get('tracks',[data['track']])]


def ui_packages():
    from wr_content_sando import catalogue
    return {path for known in catalogue().values() for path in known.get('ui_packages',[])}


def check_files(manager, folder, expected):
    for name,info in expected.items():
        path=folder/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=info['size'] or manager.hashes.file(path)!=info['sha256']:
            raise ValueError('Publicación externa incompleta o sin revisar: '+name)


def prepare_one(manager, folder, identity, stage_id, known, destination):
    from wr_content_catalog import read_menu
    if identity['schema'] not in known['compatible_schemas']:
        raise ValueError('Mod externo incompatible con esta build: '+stage_id)
    check_files(manager,folder,known['files'])
    contents=manager.tools.listing(folder/(known['stem']+'.utoc'))
    if any(p in TABLES for p in contents) or not set(known['level_paths'])<=set(contents):
        raise ValueError('El contenido del nivel no coincide con la publicación revisada')
    candidates=[folder,folder.parent/known['installer_registry']]
    source=next((p for p in candidates if all((p/name).is_file() for name in known['companion'])),None)
    if source is None:
        raise ValueError('Primera integración: falta el registro original de '+known['display_name'])
    check_files(manager,source,known['companion'])
    stamp=(inventory_stamp(folder),inventory_stamp(source))
    toc=source/next(n for n in known['companion'] if n.endswith('.utoc'))
    manager.log('Integrando '+known['display_name']+' desde sus archivos originales…')
    with tx.temporary_directory(manager.state,prefix='adopt-') as temp:
        scratch=Path(temp)
        tables=read_menu(manager,toc,scratch)
        selected={}
        for relative,asset in tables.items():
            keys=set(known['rows'].get(Path(relative).stem,[]))
            part=deepcopy(asset)
            part['Exports'][0]['Table']['Data']=[r for r in _rows(asset) if r['Name'] in keys]
            if set(r['Name'] for r in _rows(part))!=keys:raise ValueError('Faltan filas revisadas en '+relative)
            if keys:selected[relative]=part
        assets={}
        for package in known['ui_packages']:
            paths=[p for p in (scratch/Path(package).parent).glob(Path(package).name+'.*') if p.suffix in ('.uasset','.uexp','.ubulk','.uptnl')]
            if not any(p.suffix=='.uasset' for p in paths):raise ValueError('Falta imagen original: '+package)
            for path in paths:
                raw=path.read_bytes()
                assets[path.relative_to(scratch).as_posix()]=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode())
        data=dict(schema='stage-content/1',producer='SandoRallyReviewed',id=stage_id,
                  track=known['tracks'][0],tracks=known['tracks'],version=known['version'],files=known['files'],
                  compatible_schemas=known['compatible_schemas'],companion=known['companion'],
                  built_with='ACR 26756580',penalty_seconds=None,display_name=known['display_name'],
                  author=known['author'],compatibility_scope='menu',catalog_origin='reviewed-external-local/1',
                  credits=known['credits'],licence=known['licence'],tables=selected,assets=assets)
        assert set(_row_map(selected,'DT_Tracks'))==set(known['tracks'])
        if stamp!=(inventory_stamp(folder),inventory_stamp(source)):raise RuntimeError('El mod cambió durante la integración')
        tx.save(destination,data)
        manager.load_manifest(destination,identity,files_root=folder)
    return destination


def prepare_incoming(manager,folder,identity,destination):
    from wr_content_sando import catalogue
    result=[]
    for stage_id,known in catalogue().items():
        if known.get('adapter')=='explicit-paths/1' and (folder/(known['stem']+'.utoc')).is_file():
            result.append(prepare_one(manager,folder,identity,stage_id,known,destination/(known['stem']+'.stage.json')))
    return result


def adopt_one(manager,folder,identity,stage_id,known):
    cached=manager.state/'catalog'/(known['stem']+'.stage.json')
    prepare_one(manager,folder,identity,stage_id,known,cached)
