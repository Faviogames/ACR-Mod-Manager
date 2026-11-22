"""Read-only stable release checks; version parsing/request pattern from wr_update."""
import json,re,urllib.error,urllib.request

def version(tag):
    if not re.fullmatch(r'v?\d+(?:\.\d+)*',str(tag)):
        raise ValueError('Unsupported release version')
    parts=tuple(map(int,tag.lstrip('v').split('.')))
    return parts+(0,)*max(0,3-len(parts))

def request(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={
        'User-Agent':'ACR-Mod-Manager','Accept':'application/vnd.github+json'}),timeout=12)

def latest(release,opener=request):
    repo=release['repository']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
        raise ValueError('Invalid update repository')
    try:
        with opener('https://api.github.com/repos/'+repo+'/releases/latest') as response:
            raw=response.read(1024*1024+1)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code==404:return dict(status='unpublished',version=release['version'])
        raise
    if len(raw)>1024*1024:raise ValueError('Release response too large')
    data=json.loads(raw)
    if data.get('draft') or data.get('prerelease'):
        return dict(status='unpublished',version=release['version'])
    tag=data['tag_name'];newer=version(tag)>version(release['version'])
    if data.get('html_url')!='https://github.com/'+repo+'/releases/tag/'+tag:
        raise ValueError('Unexpected release URL')
    downloadable=any((asset.get('name')=='ACR-Mod-Manager-Setup.exe' or asset.get('name','').startswith('ACR-Mod-Manager-') and asset['name'].endswith('.zip'))
        and asset.get('browser_download_url')=='https://github.com/'+repo+'/releases/download/'+tag+'/'+asset['name']
        for asset in data.get('assets',[]))
    return dict(status='available' if newer and downloadable else 'current' if not newer else 'preparing',version=tag)
