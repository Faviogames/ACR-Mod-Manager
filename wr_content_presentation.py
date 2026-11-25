"""Preserve user-edited addon presentation; native baseline and gameplay rows stay fresh."""
from copy import deepcopy
from pathlib import Path
import base64,hashlib
from wr_content_imports import remap_row
from wr_menu_tables import _rows,_row_map,_field,_references

FIELDS={'DT_Tracks':{'Name','TrackImage','LobbyTrackImage'},
        'DT_TracksVariants':{'Name','VariantImage','LobbyVariantImage'},
        'DT_TracksLocations':{'Name','HistoryAndTrivia','Logo','Background','BackgroundImage'}}
DEPENDENCIES={'TracksTextures','TracksLocationsLogos','TracksLocationsBackgrounds'}
POLICY=2
LEGACY_IMAGE_PLACEHOLDERS={'HafrenSouthTrack','HafrenSouthBackground'}
LEGACY_DESCRIPTION='Stages imported from WRC Generations. Free Practice only.'

def snapshot(manager,identity):
    from wr_content import read
    result={}
    for path in (manager.state/'catalog').glob('*.stage.json'):
        try:
            data=read(path)
            if data.get('producer')!='StageExporter':continue
            folder=next((folder for folder in (manager.mods,manager.disabled)
                         if all((folder/name).is_file() for name in data.get('files',{}))),None)
            if folder is None:continue
            manager.load_manifest(path,identity,files_root=folder)
            result[data['track']]=data
        except (ValueError,KeyError,OSError):continue
    return result

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for v in value.values():yield from strings(v)
    elif isinstance(value,list):
        for v in value:yield from strings(v)

def packages(value):
    return {s.split('.')[0].replace('/Game/','acr/Content/',1) for s in strings(value)
            if s.startswith('/Game/Data/UITextures/') and Path(s).name.startswith('T_Wrcg')}

def canonical(prop,asset):
    if prop is None:return None
    refs=list(_references(prop))
    if refs:return {'references':refs}
    if 'CultureInvariantString' in prop:
        return {'text':prop.get('CultureInvariantString') if prop.get('CultureInvariantString') is not None else prop.get('Value')}
    return remap_row(prop,asset,{'Imports':[]}) if prop is not None else None

def preserve(records,previous,tables,legacy):
    """Three-way presentation merge: last managed definition, current menu, new catalogue."""
    for record in records:
        data=record['data']
        if data.get('producer')!='StageExporter' or not record.get('internal'):continue
        old=previous.get(data['track'],{})
        overrides=deepcopy(old.get('presentation_overrides',dict(fields={},packages=[])))
        copied=set();pending=set();changed=False
        absent_from_menu=data['track'] not in _row_map(tables,'DT_Tracks')
        def dependency(table,key):
            nonlocal changed
            if table not in DEPENDENCIES or (table,key) in copied:return
            name='DT_'+table
            source_tables=tables if key in _row_map(tables,name) else old.get('tables',{})
            source_path=next((p for p in source_tables if Path(p).stem==name),None)
            if source_path is None:return
            source=source_tables[source_path];row=_row_map(source_tables,name).get(key)
            if row is None:raise ValueError('Missing installed presentation dependency: '+table+'/'+key)
            refs=packages(row)
            if not refs:return  # Native art remains referenced from native tables, never redistributed.
            if source_path not in data['tables']:
                data['tables'][source_path]=dict(Imports=[],Exports=[dict(Table=dict(Data=[]))])
            target=data['tables'][source_path];rows=_rows(target)
            rows[:]=[r for r in rows if r['Name']!=key];rows.append(remap_row(row,source,target))
            copied.add((table,key));pending.update(refs);changed=True
        for path,target in list(data['tables'].items()):
            table=Path(path).stem
            if table not in FIELDS or path not in tables:continue
            source=tables[path]
            for row in _rows(target):
                source=tables[path]
                installed=_row_map(tables,table).get(row['Name'])
                original=_row_map(old.get('tables',{}),table).get(row['Name'])
                remembered=overrides['fields'].get(path,{}).get(row['Name'],[])
                if installed is None and remembered and original is not None:
                    installed=original;source=old['tables'][path]
                if installed is None:continue
                for name in FIELDS[table]:
                    value=_field(installed,name);before=_field(original,name) if original else None
                    dest=_field(row,name)
                    if value is None or dest is None:continue
                    if not list(strings(value)):continue
                    if name.endswith('Image') and table!='DT_TracksLocations':
                        refs=list(_references(value))
                        desired=list(_references(dest))
                        if any(t=='TracksTextures' and k in LEGACY_IMAGE_PLACEHOLDERS for t,k in refs) and any(t=='TracksTextures' and k.startswith(data['track']+'_') for t,k in desired):
                            if name in remembered:remembered.remove(name);changed=True
                            continue
                        if refs and before is None and not any(t=='TracksTextures' and k.startswith(data['track']+'_') for t,k in refs):continue
                    if name=='HistoryAndTrivia' and value.get('CultureInvariantString')==LEGACY_DESCRIPTION and dest.get('CultureInvariantString') not in (None,'',LEGACY_DESCRIPTION):
                        if name in remembered:remembered.remove(name);changed=True
                        continue
                    if name=='HistoryAndTrivia' and before is None and not (value.get('CultureInvariantString') or value.get('Value')):continue
                    local_source=old.get('catalog_origin')=='official-local-adoption'
                    if name.endswith('Image') and table!='DT_TracksLocations':
                        local_source=local_source and any(t=='TracksTextures' and k.startswith(data['track']+'_') for t,k in _references(value))
                    if name in remembered or local_source or canonical(value,source)!=canonical(before,old.get('tables',{}).get(path,source)):
                        replacement=remap_row(value,source,target);row['Value'][row['Value'].index(dest)]=replacement
                        names=overrides['fields'].setdefault(path,{}).setdefault(row['Name'],[])
                        if name not in names:names.append(name)
                        for table_name,key in _references(value):dependency(table_name,key)
                        pending.update(packages(value));changed=True
        # Detect pixels changed outside the manager even when the texture path stayed the same.
        relevant=set(data.get('assets',{}))|set(old.get('assets',{}))
        for relative in relevant:
            if not relative.endswith(('.uexp','.ubulk')):continue
            current=Path(legacy)/relative;before=old.get('assets',{}).get(relative)
            if not current.is_file() or before is None:continue
            package=relative.rsplit('.',1)[0]
            if package in overrides['packages'] or hashlib.sha256(current.read_bytes()).hexdigest()!=before['sha256']:
                pending.add(package)
        for package in set(overrides['packages'])|pending:
            if not package.startswith('acr/Content/Data/UITextures/') or not Path(package).name.startswith('T_Wrcg'):
                raise ValueError('Unmanaged presentation asset rejected')
            files=[p for p in (Path(legacy)/Path(package).parent).glob(Path(package).name+'.*') if p.suffix in ('.uasset','.uexp','.ubulk','.uptnl')]
            if not any(p.suffix=='.uasset' for p in files):
                saved={p:r for p,r in old.get('assets',{}).items() if p.rsplit('.',1)[0]==package}
                if absent_from_menu and package+'.uasset' in saved:
                    data.setdefault('assets',{}).update(deepcopy(saved));changed=True
                    if package not in overrides['packages']:overrides['packages'].append(package)
                    continue
                raise ValueError('Missing installed custom image: '+package)
            for file in files:
                raw=file.read_bytes();data.setdefault('assets',{})[file.relative_to(legacy).as_posix()]=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode())
            if package not in overrides['packages']:overrides['packages'].append(package)
            changed=True
        if changed:
            data['presentation_overrides']=overrides
            record['_presentation_changed']=True

def retain_installed(manager,records,previous):
    from wr_content import NAME
    from wr_content_catalog import read_menu
    import wr_content_transaction as tx
    toc=manager.mods/(NAME+'.utoc')
    if not toc.is_file():return
    with tx.temporary_directory(manager.state,prefix='adopt-') as temporary:
        legacy=Path(temporary);tables=read_menu(manager,toc,legacy)
        preserve(records,previous,tables,legacy)
