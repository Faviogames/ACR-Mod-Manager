"""Developer rebuild of addon presentation from current author inputs; preserves all stage versions."""
from pathlib import Path
from copy import deepcopy
import argparse,base64,hashlib,json,os,subprocess
from wr_content import read,digest
from wr_content_transaction import save
from wr_menu_tables import _rows,_row_map,_field

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for child in value.values():yield from strings(child)
    elif isinstance(value,list):
        for child in value:yield from strings(child)

def soft_path(row,package):
    def visit(v):
        if isinstance(v,dict):
            if 'PackageName' in v and 'AssetName' in v:v.update(PackageName=package,AssetName=package.rsplit('/',1)[1])
            for x in v.values():visit(x)
        elif isinstance(v,list):
            for x in v:visit(x)
    visit(row)

def ref(row,name,key):
    field=_field(row,name)
    if field:
        for value in field.get('Value',[]):
            if value.get('Name')=='Row':value['Value']=key

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exporter',type=Path,required=True);parser.add_argument('--worker',type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parent;database=read(root/'official_database.json');catalog=read(root/'official_catalog.json')
    descriptions=read(args.exporter/'custom/descriptions.json',{})
    description_sha=hashlib.sha256((args.exporter/'custom/descriptions.json').read_bytes()).hexdigest()
    jobs={};inputs={}
    def cook(source,package,size):
        jobs[package]=dict(source=str(source),package=package,size=size)
        inputs[str(source.relative_to(args.exporter))]=hashlib.sha256(source.read_bytes()).hexdigest()
    proto=next((deepcopy(a),deepcopy(r)) for d in database['stages'].values() for p,a in d['tables'].items() if Path(p).stem=='DT_TracksTextures' for r in _rows(a))
    for track,definition in database['stages'].items():
        tables=definition['tables'];slug=catalog['stages'][track]['slug'];slots={}
        for slot,size in (('Card',[1720,448]),('Background',[1325,922]),('Lobby',[170,100])):
            source=next((p for p in (args.exporter/'custom/images'/slug/(slot.lower()+'.png'),args.exporter/'custom/images'/slug.removesuffix('r')/(slot.lower()+'.png')) if p.is_file()),None)
            if source is None:continue
            package='/Game/Data/UITextures/Tracks/Wrcg/T_'+track+'_'+slot
            cook(source,package,size);slots[slot]=track+'_'+slot
            path='TrackSelection/DT_TracksTextures.uasset'
            if path not in tables:
                tables[path]=deepcopy(proto[0]);tables[path]['Exports'][0]['Table']['Data']=[]
            row=deepcopy(proto[1]);row['Name']=slots[slot];soft_path(row,package)
            rows=_rows(tables[path]);rows[:]=[r for r in rows if r['Name']!=row['Name']];rows.append(row)
        if slots:
            trackrow=_row_map(tables,'DT_Tracks')[track]
            for field in ('TrackImage','LobbyTrackImage'):ref(trackrow,field,slots.get('Background') or slots.get('Card') or slots['Lobby'])
            for row in _row_map(tables,'DT_TracksVariants').values():
                ref(row,'VariantImage',slots.get('Card') or slots.get('Background') or slots['Lobby'])
                ref(row,'LobbyVariantImage',slots.get('Lobby') or slots.get('Card') or slots['Background'])
        for location,row in _row_map(tables,'DT_TracksLocations').items():
            if location in descriptions:
                field=_field(row,'HistoryAndTrivia');assert field is not None
                field.update(CultureInvariantString=descriptions[location],Flags='CultureInvariant',HistoryType='None',Value=None)
            for slot,table,size in (('logo','DT_TracksLocationsLogos',[485,218]),('background','DT_TracksLocationsBackgrounds',[406,737])):
                source=args.exporter/'custom/images'/location/(slot+'.png')
                if not source.is_file():continue
                package='/Game/Data/UITextures/Tracks/Wrcg/T_'+location+slot.capitalize()
                cook(source,package,size)
                target=_row_map(tables,table).get(location);assert target is not None,(track,table,location)
                soft_path(target,package)
    save(root/'authored-plan.json',list(jobs.values()))
    worker=args.worker or root/'exporter/_internal/wrcg2acr-worker.exe'
    if not worker.is_file():raise ValueError('Use an isolated developer worker with --worker; the standalone app does not bundle the exporter core')
    subprocess.run([str(worker),'-m','_cm_cook_authored'],check=True,cwd=worker.parent.parent,
                   env=dict(os.environ,ACR_CM_ART_BUILD_ROOT=str(root)),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for relative,sha in inputs.items():assert hashlib.sha256((args.exporter/relative).read_bytes()).hexdigest()==sha,'Input changed while cooking'
    legacy=root/'authored-legacy'
    for file in legacy.rglob('*'):
        if file.is_file():
            raw=file.read_bytes();database['assets'][file.relative_to(legacy).as_posix()]=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode())
    used=set()
    for track,definition in database['stages'].items():
        packages={value.split('.')[0].replace('/Game/','acr/Content/',1) for value in strings(definition['tables']) if value.startswith('/Game/Data/UITextures/') and Path(value).name.startswith('T_Wrcg')}
        assets=sorted(name for name in database['assets'] if str(Path(name).with_suffix('')).replace('\\','/') in packages)
        assert all(p+'.uasset' in assets for p in packages),(track,'Missing authored asset')
        definition['assets']=assets;used.update(assets)
        definition['definition_revision']=digest(dict(tables=definition['tables'],assets={p:database['assets'][p]['sha256'] for p in assets}))
        assert all(r['Name'].startswith('Wrcg') for a in definition['tables'].values() for r in _rows(a))
    database['assets']={p:database['assets'][p] for p in sorted(used)}
    assert hashlib.sha256((args.exporter/'custom/descriptions.json').read_bytes()).hexdigest()==description_sha,'Descriptions changed while cooking'
    database['authored_inputs']=inputs;database['descriptions_sha256']=description_sha
    save(root/'official_database.json',database)
    save(root/'official_presentation.json',dict(schema='official-presentation/1',revisions={t:d['definition_revision'] for t,d in database['stages'].items()}))
    print('Rebuilt:',len(database['stages']),'definitions;',len(jobs),'current authored textures;',len(database['assets']),'asset files',flush=True)

if __name__=='__main__':main()
