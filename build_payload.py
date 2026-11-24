"""Build a clean installer payload from an explicit runtime allowlist."""
from pathlib import Path
import json,zipfile
ROOT=Path(__file__).resolve().parent
FILES=['wr_content.py','wr_content_app.py','wr_content_catalog.py','wr_content_imports.py','wr_content_tools.py','wr_content_transaction.py','wr_content_physics.py','wr_content_updates.py','wr_content_sando.py','wr_content_cleanup.py','wr_content_steam.py','third_party_catalog.json','wr_menu_tables.py','wr_iostore_compress.py','app_release.json','official_catalog.json','official_database.json','physics_recipe.json','compatibility.json','INICIAR_GESTOR.bat']
files=[(ROOT/name,name) for name in FILES]
files.append((ROOT/'USER_GUIDE.txt','README.txt'))
files += [(ROOT/'desktop-next/ACR Pak Manager.exe','desktop-bin/ACR Pak Manager.exe')]
for directory in ('python','bin','ui','art','licenses'):
 for path in sorted((ROOT/directory).rglob('*')):
  if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc' and path.name.lower() != 'oo2core_9_win64.dll':files.append((path,path.relative_to(ROOT).as_posix()))
assert all(path.is_file() for path,_ in files)
assert len({name.casefold() for _,name in files})==len(files)
assert not any(name.startswith(('local/','reference/','work/','tests/','custom/')) or Path(name).suffix in ('.pak','.utoc','.ucas') or Path(name).name.startswith('tools.cp') for _,name in files)
(ROOT/'dist').mkdir(exist_ok=True)
with zipfile.ZipFile(ROOT/'dist/payload.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
 for path,name in files:archive.write(path,name)
with zipfile.ZipFile(ROOT/'dist/payload.zip') as archive:
 assert archive.testzip() is None
 report=dict(files=len(files),installed_bytes=sum(p.stat().st_size for p,_ in files),payload_zip_bytes=(ROOT/'dist/payload.zip').stat().st_size,private_data_included=False,level_packages_included=False,closed_exporter_core_included=False)
 (ROOT/'dist/payload-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(report,flush=True)
