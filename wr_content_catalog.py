"""Official stage catalogue + local adoption database. Users need no sidecars.

Only addon rows are recovered from existing menus. Native baseline tables are
always freshly extracted by Manager.synchronize, never adopted from these menus.
"""
from pathlib import Path
import json
import os
import shutil
import tempfile
from copy import deepcopy

from wr_content import (EXTS, MAIN, TABLES, inventory_stamp, is_menu, read, register)
from wr_content_tools import run
from wr_content_transaction import save
from wr_menu_tables import _row_map

ROOT=Path(__file__).resolve().parent


def official_catalog():
    catalog=read(ROOT/'official_catalog.json', {})
    if catalog.get('schema')!='stage-exporter-official/1':
        return {}
    return catalog.get('stages', {})


def retain_menu(manager,source):
    if source.is_relative_to(manager.state/'menu-sources'):
        return
    saved=manager.state/'menu-sources/adopted'/manager.hashes.file(source)
    saved.mkdir(parents=True,exist_ok=True)
    for ext in EXTS:
        original=source.with_suffix(ext)
        if original.is_file() and not (saved/original.name).exists():
            shutil.copy2(original,saved/original.name)


def prepare_incoming(manager,folder,identity,destination):
    """Match bare official packs to known internal definitions, without sidecars."""
    result=[]
    templates=[read(p) for p in (manager.state/'catalog').glob('*.stage.json')]
    database=read(ROOT/'official_database.json',{})
    catalog=official_catalog()
    for toc in sorted(folder.glob('pakchunk99-Wrcg*.utoc')):
        if is_menu(toc.stem):
            continue
        digest=manager.hashes.file(toc)
        bundled=next((track for track,data in database.get('stages',{}).items() if digest in data['versions']),None)
        if bundled is None:
            levels=[Path(p).stem for p in manager.tools.listing(toc) if p.startswith('acr/Content/Levels/Wrcg') and p.endswith('.umap')]
            if len(levels)==1 and database.get('stages',{}).get(levels[0],{}).get('allow_rebuilds'):
                bundled=levels[0]
        if bundled:
            path=destination/(toc.stem+'.stage.json')
            from_official_database(manager,folder,toc,bundled,catalog[bundled],database,identity,output_path=path)
            result.append(path)
            continue
        template=next((data for data in templates if any(name.endswith('.utoc') and row['sha256']==digest
                      for name,row in data['files'].items())),None)
        if template is None:
            raise ValueError('Esta versión de '+toc.name+' aún no está en la base de datos oficial local')
        data=deepcopy(template)
        data['files']={}
        for ext in EXTS:
            file=toc.with_suffix(ext)
            if not file.is_file():
                raise ValueError('Paquete incompleto: '+file.name)
            data['files'][file.name]=dict(size=file.stat().st_size,sha256=manager.hashes.file(file))
        path=destination/(toc.stem+'.stage.json')
        save(path,data)
        manager.load_manifest(path,identity,files_root=folder)
        result.append(path)
    if not result:
        foreign=sorted(p.name for p in folder.glob('*.utoc') if not p.name.startswith('pakchunk99-Wrcg'))
        if foreign:
            raise ValueError('Mod externo no soportado: '+', '.join(foreign))
        raise ValueError('No se han encontrado paquetes oficiales en la carpeta seleccionada')
    return result


def from_official_database(manager,folder,toc,track,entry,database,identity,output_path=None):
    definition=database.get('stages',{}).get(track)
    if definition is None:
        return False
    header=manager.hashes.file(toc)
    version=definition['versions'].get(header)
    if version is None:
        if not definition.get('allow_rebuilds'):
            return False
        manager.log('Comprobando integridad de '+entry['name']+'…')
        run(manager.tools.ret,'verify',toc)
        version=dict(version=header[:12],files={ext:dict(size=toc.with_suffix(ext).stat().st_size,sha256=manager.hashes.file(toc.with_suffix(ext))) for ext in EXTS})
    files={}
    for ext in EXTS:
        file=toc.with_suffix(ext)
        expected=version['files'][ext]
        if file.stat().st_size!=expected['size'] or manager.hashes.file(file)!=expected['sha256']:
            raise ValueError('El paquete oficial no coincide con su versión: '+file.name)
        files[file.name]=dict(expected)
    data=dict(schema='stage-content/1',producer='StageExporter',id=definition['id'],track=track,
              version=version['version'],files=files,tables=deepcopy(definition['tables']),
              assets={name:database['assets'][name] for name in definition['assets']},
              penalty_seconds=definition['penalty_seconds'],built_with=definition['built_with'],
              compatible_schemas=definition['compatible_schemas'],
              compatibility_scope=definition.get('compatibility_scope','full'),catalog_origin='bundled-official-database')
    if entry.get('preview'):
        import base64,hashlib
        raw=(ROOT/entry['preview']).read_bytes()
        data['preview']=dict(data=base64.b64encode(raw).decode(),size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    path=Path(output_path) if output_path is not None else manager.state/'catalog'/(toc.stem+'.stage.json')
    save(path,data)
    manager.load_manifest(path,identity,files_root=folder)
    manager.log('Reconocido desde la base oficial: '+entry['name'])
    return True


def read_menu(manager, toc, destination):
    """Resolve imports through a fresh native catalog plus one selected donor menu."""
    contents=manager.tools.listing(toc)
    with manager.tools.stock_view(destination) as view:
        sources=[toc]
        sources += [p for p in manager.mods.glob('pakchunk99-Wrcg*.utoc') if not is_menu(p.stem)]
        for source in sources:
            for ext in ('.utoc','.ucas'):
                source_file=source.with_suffix(ext)
                if not source_file.is_file():
                    raise ValueError('Contenedor incompleto: '+str(source_file))
                target=view/source_file.name
                try:
                    os.link(source_file,target)
                except OSError:
                    # Only small external donor menus may be on another drive.
                    if source_file.stat().st_size>128*1024*1024:
                        raise RuntimeError('El catálogo temporal debe estar en el disco del juego')
                    shutil.copy2(source_file,target)
        filters=['Data/Database/Main/Common/DT_Levels','Data/Database/Main/TrackSelection/DT_']
        filters += [p.removeprefix('acr/Content/').removesuffix('.uasset') for p in contents
                    if p.startswith(('acr/Content/Data/UITextures/','acr/Content/Environments/WrcgShared/PhysicalMaterials/'))
                    or Path(p).stem in ('PM_SurfaceSnow','PM_SurfaceDeepSnow')]
        for selected in filters:
            run(manager.tools.ret,'to-legacy',view,destination,'-f',selected,'--version','UE5_6','--no-shaders')
    tables={}
    for relative in sorted(TABLES):
        path=destination/relative
        if path.is_file():
            tables[relative[len(MAIN):]]=manager.tools.dump(path,destination)
    return tables


def cached_record(manager, folder, toc, identity):
    path=manager.state/'catalog'/(toc.stem+'.stage.json')
    if not path.is_file():
        return False
    # Reject cache from another game schema; never silently bless old geometry.
    try:
        manager.load_manifest(path,identity,files_root=folder)
        return True
    except ValueError as exc:
        if str(exc).startswith(('SHA256 incorrecto:', 'Archivo ausente o tamaño incorrecto:')):
            return False
        raise


def adopt_installed(manager, identity):
    catalog=official_catalog()
    if not catalog:
        return
    pending=[]
    for folder in (manager.mods,manager.disabled):
        for toc in sorted(folder.glob('pakchunk99-Wrcg*.utoc')):
            if is_menu(toc.stem) or toc.with_name(toc.stem+'.stage.json').exists():
                continue
            if cached_record(manager,folder,toc,identity):
                continue
            contents=manager.tools.listing(toc)
            levels=[p for p in contents if p.startswith('acr/Content/Levels/Wrcg') and p.endswith('.umap')]
            if len(levels)!=1:
                raise ValueError('No se identifica un único nivel oficial: '+toc.name)
            track=Path(levels[0]).stem
            entry=catalog.get(track)
            if entry is None:
                raise ValueError('El catálogo oficial necesita una actualización para '+track)
            for ext in EXTS:
                if not toc.with_suffix(ext).is_file():
                    raise ValueError('Paquete incompleto: '+toc.stem)
            pending.append((folder,toc,track,entry))
    if not pending:
        return
    database=read(ROOT/'official_database.json',{})
    if database and database.get('schema')!='stage-exporter-database/1':
        raise ValueError('Versión de base de datos oficial no admitida')
    unresolved=[]
    for folder,toc,track,entry in pending:
        if not from_official_database(manager,folder,toc,track,entry,database,identity):
            unresolved.append((folder,toc,track,entry))
    pending=unresolved
    if not pending:
        manager.hashes.save()
        return
    manager.log('Reconociendo '+str(len(pending))+' tramos oficiales; creando la base de datos local…')
    before=(inventory_stamp(manager.mods),inventory_stamp(manager.disabled))
    sources=list(sorted(p for p in manager.mods.glob('*.utoc') if is_menu(p.stem)))
    sources += sorted((manager.state/'menu-sources/adopted').glob('*/*.utoc'), reverse=True)
    for folder in manager.config.get('menu_sources',[]):
        sources.extend(p for p in Path(folder).glob('*.utoc') if is_menu(p.stem))
    missing={track for _,_,track,_ in pending}
    with tempfile.TemporaryDirectory(dir=manager.state,prefix='adopt-') as temp:
        scratch=Path(temp)
        for i,source in enumerate(sources):
            destination=scratch/str(i);destination.mkdir()
            manager.log('Recuperando registros e imágenes de '+source.name+'…')
            tables=read_menu(manager,source,destination)
            available=set(_row_map(tables,'DT_Tracks'))
            # Retain the small source menu for later official packs after the old
            # universal menu has been replaced. Never use its native rows as baseline.
            retain_menu(manager,source)
            for folder,toc,track,entry in pending:
                if track not in missing or track not in available:
                    continue
                cached=manager.state/'catalog'/(toc.stem+'.stage.json')
                prepared=scratch/'records'/cached.name
                preview=ROOT/entry['preview'] if entry.get('preview') else None
                path=register(manager,legacy=destination,pak=toc,track=track,stage_id=entry['id'],
                    version=manager.hashes.file(toc)[:12],built_with=identity['schema'],penalty=True,
                    preview=preview,output_path=prepared)
                data=read(path)
                data['built_with']='Desconocida · paquete existente'
                data['compatibility_scope']='menu'
                data['catalog_origin']='official-local-adoption'
                save(cached,data)
                missing.remove(track)
                manager.log('Registrado automáticamente: '+entry['name'])
            if not missing:
                break
    if before!=(inventory_stamp(manager.mods),inventory_stamp(manager.disabled)):
        raise RuntimeError('Los paquetes cambiaron durante el reconocimiento; repite la operación')
    manager.hashes.save()
    if missing:
        raise ValueError('La base oficial aún no incluye esta publicación de '+', '.join(sorted(missing))+
                         '. Se necesita actualizar el catálogo de la app.')
