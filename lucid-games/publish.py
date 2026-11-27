"""Verify the pinned upstream release and build the offline collection."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, zipfile
BASE='https://lucid-game-launcher.maxfaine.chatgpt.site'
root=Path(__file__).resolve().parent
pins=json.loads((root/'release.json').read_text())
out=Path('artifacts')
out.mkdir()
if 'verifiedGitHubBuild' in pins:
    from verified_collection import publish_verified
    build_pins=dict(pins)
    if 'sourceBase' in pins:
        build_pins['source']=pins['sourceBase']
    publish_verified(root, out, build_pins, pins['verifiedGitHubBuild'])
    if 'sourceBase' in pins:
        source=out/pins['source']['name']
        refreshed=out/'.refreshed-source.zip'
        subprocess.run([
            'python3',str(root/'refresh_source.py'),str(source),str(refreshed),'--root',str(root)
        ],check=True)
        with refreshed.open('rb') as stream:
            actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=pins['source']['sha256'] or refreshed.stat().st_size!=pins['source']['bytes']:
            raise RuntimeError('Refreshed source archive does not match the release pin')
        os.replace(refreshed,source)
        checks=[]
        for path in sorted(out.iterdir()):
            if path.is_file() and path.name!='SHA256SUMS.txt':
                with path.open('rb') as stream:
                    checks.append(hashlib.file_digest(stream,'sha256').hexdigest()+'  '+path.name+'\n')
        (out/'SHA256SUMS.txt').write_text(''.join(checks))
    raise SystemExit(0)
def fetch(url, path, expected, module=False):
    args=['curl','--fail','--location','--silent','--show-error','--retry','4']
    if module:args+=['--header','X-Lucid-Install: 1']
    subprocess.run(args+['--output',str(path),BASE+url],check=True)
    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=expected['sha256'] or path.stat().st_size!=expected['bytes']:
        raise RuntimeError(f'Upstream release changed: {url}')
    return digest
catalog=json.loads((root/'catalog.json').read_text())
dirs={'windows-x64':'Windows','linux-x64':'Linux','macos-arm64':'macOS-Apple-Silicon','macos-x64':'macOS-Intel'}
assert len(catalog['modules'])==11 and {f['platform'] for f in pins['desktop']}==set(dirs)
checks={}
def add(z, path, name):
    info=zipfile.ZipInfo(name,(2026,1,1,0,0,0))
    info.create_system=3
    info.external_attr=0o100644<<16
    info.file_size=path.stat().st_size
    with path.open('rb') as src,z.open(info,'w') as dst:
        shutil.copyfileobj(src,dst,1024*1024)
with zipfile.ZipFile(out/'Lucid-Games-Complete.zip','w',allowZip64=True) as z:
    add(z,root/'README.md','README.md')
    add(z,root/'catalog.json','Lucid Content/catalog.json')
    for g in catalog['modules']:
        tmp=Path('module.tmp')
        fetch(g['url'],tmp,g,True)
        add(z,tmp,'Lucid Content/'+g['id']+'-'+g['version']+'.lgm')
        tmp.unlink()
    for f in pins['desktop']:
        tmp=Path(f['name'])
        fetch('/download/'+f['platform'],tmp,f)
        add(z,tmp,dirs[f['platform']]+'/'+f['name'])
        tmp.unlink()
source=out/'Lucid-Games-Launcher-Source.zip'
checks[source.name]=fetch('/download/source',source,pins['source'])
subprocess.run(['python3',str(source),'--verify'],check=True)
bundle=out/'Lucid-Games-Complete.zip'
with bundle.open('rb') as stream:checks[bundle.name]=hashlib.file_digest(stream,'sha256').hexdigest()
if checks[bundle.name]!=pins['bundleSha256']:
    raise RuntimeError('Combined archive checksum mismatch')
for item in pins['mobile']:
    platform=item['platform']
    if platform not in ('android','ios'):
        raise ValueError('Unexpected mobile target')
    package=out/item['name']
    checks[package.name]=fetch('/download/'+platform,package,item)
(out/'SHA256SUMS.txt').write_text(''.join(h+'  '+n+'\n' for n,h in checks.items()))
