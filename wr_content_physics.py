"""Generate the shared WRCG material registry from THIS game's native assets.

The ordering/aliases follow wr_native_compat; only authored wood overrides and
import identifiers are bundled. No native material or registry file is shipped.
"""
from copy import deepcopy
from pathlib import Path
from wr_content_imports import remap_row
from wr_content_tools import run
from wr_menu_tables import _add_names

ROOT=Path(__file__).resolve().parent
PARENT='/Game/Data/Gameplay/PhysicalMaterials/'
SHARED='/Game/Environments/WrcgShared/PhysicalMaterials/'


def rename(asset,old,new):
    names={old:new,old.rsplit('/',1)[-1]:new.rsplit('/',1)[-1]}
    def walk(value):
        if isinstance(value,str):return names.get(value,value)
        if isinstance(value,list):return [walk(v) for v in value]
        if isinstance(value,dict):return {k:walk(v) for k,v in value.items()}
        return value
    return walk(asset)


def material_packages(asset):
    values=next(p['Value'] for p in asset['Exports'][0]['Data'] if p['Name']=='PhysicalMaterials')
    result=[]
    for value in values:
        index=value['Value']
        if not isinstance(index,int) or not 0 < -index <= len(asset['Imports']):
            raise ValueError('Invalid physical material reference')
        item=asset['Imports'][-index-1]
        outer=item['OuterIndex']
        if not 0 < -outer <= len(asset['Imports']):raise ValueError('Invalid physical material package')
        result.append(asset['Imports'][-outer-1]['ObjectName'])
    return result


def registry(native,order):
    data=deepcopy(native)
    field=next(p for p in data['Exports'][0]['Data'] if p['Name']=='PhysicalMaterials')
    existing=dict(zip(material_packages(data),field['Value']))
    wanted=list(dict.fromkeys([*order,*existing]))
    sample=field['Value'][0]
    obj=deepcopy(data['Imports'][-sample['Value']-1])
    pkg=deepcopy(data['Imports'][-obj['OuterIndex']-1])
    def imp(value):
        if value not in data['Imports']:data['Imports'].append(value)
        return -data['Imports'].index(value)-1
    values=[]
    for i,package in enumerate(wanted):
        item=deepcopy(existing.get(package,sample));item['Name']=str(i)
        if package not in existing:
            parent=dict(pkg,ObjectName=package,OuterIndex=0)
            child=dict(obj,ObjectName=package.rsplit('/',1)[-1],OuterIndex=imp(parent))
            item['Value']=imp(child)
        values.append(item)
    field['Value']=values
    return data


def build_shared(manager,legacy,scratch):
    from wr_content import read
    recipe=read(ROOT/'physics_recipe.json')
    if recipe.get('schema')!='stage-exporter-physics/1':raise ValueError('Missing physics compatibility recipe')
    manager.log('Generando los materiales compartidos desde los originales de ACR…')
    native=scratch/'physics-native'
    donors=['PM_SurfaceKerb','DA_PhysMaterialsMappingCommon','PM_SurfaceSnowSweden','PM_SurfaceDeepSnowSweden']
    with manager.tools.stock_view(scratch) as view:
        for name in donors:
            run(manager.tools.ret,'to-legacy',view,native,'-f','Data/Gameplay/PhysicalMaterials/'+name,
                '--version','UE5_6','--no-shaders')
    def load(name):
        return manager.tools.dump(native/('acr/Content/Data/Gameplay/PhysicalMaterials/'+name+'.uasset'),scratch)
    def write(data,package):
        path=legacy/'acr/Content'/(package.removeprefix('/Game/')+'.uasset')
        manager.tools.write(data,path,scratch)
        return manager.tools.dump(path,scratch)
    wood=rename(load('PM_SurfaceKerb'),PARENT+'PM_SurfaceKerb',SHARED+'PM_WrcgWood')
    wood['Exports'][0]['Data']=remap_row(recipe['wood_properties'],{'Imports':recipe['wood_imports']},wood)
    _add_names(wood,[{'Name':n} for n in recipe['wood_names']])
    write(wood,SHARED+'PM_WrcgWood')
    mapping=registry(load('DA_PhysMaterialsMappingCommon'),recipe['physics_order'])
    mapping=rename(mapping,PARENT+'DA_PhysMaterialsMappingCommon',SHARED+'DA_WrcgPhysMaterialsMapping')
    actual=write(mapping,SHARED+'DA_WrcgPhysMaterialsMapping')
    if material_packages(actual)!=material_packages(mapping):raise ValueError('Shared registry ordering changed on write')
    for old,new in (('PM_SurfaceSnow','PM_SurfaceSnowSweden'),('PM_SurfaceDeepSnow','PM_SurfaceDeepSnowSweden')):
        write(rename(load(new),PARENT+new,PARENT+old),PARENT+old)
    return dict(physical_materials=len(material_packages(actual)),wood=True,snow_aliases=True)
