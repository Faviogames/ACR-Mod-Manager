"""Developer build: refresh every available authored preview, without a stage allowlist."""
from pathlib import Path
import argparse,hashlib,shutil
from wr_content import read
from wr_content_transaction import save

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exporter',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parent
    catalog=read(root/'official_catalog.json',dict(schema='stage-exporter-official/1',stages={}))
    count=0
    for track,entry in catalog['stages'].items():
        slug=entry['slug'];folder=args.exporter/'custom/images'
        source=next((p for p in (folder/slug/'background.png',folder/slug.removesuffix('r')/'background.png') if p.is_file()),None)
        if source is None:continue
        raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        target=root/'art'/(digest+'.png');target.parent.mkdir(exist_ok=True)
        if not target.exists():
            temporary=target.with_suffix('.new');temporary.write_bytes(raw);temporary.replace(target)
        entry['preview']=target.relative_to(root).as_posix();entry['preview_sha256']=digest
        count+=1
    save(root/'official_catalog.json',catalog)
    print('Authored previews refreshed:',count,'of',len(catalog['stages']),flush=True)

if __name__=='__main__':main()
