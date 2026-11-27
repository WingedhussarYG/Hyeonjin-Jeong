"""Verify the pinned upstream release and build the offline collection."""
from pathlib import Path
import hashlib, json, shutil, subprocess, zipfile
BASE='https://lucid-game-launcher.maxfaine.chatgpt.site'
root=Path(__file__).resolve().parent
pins=json.loads((root/'release.json').read_text())
out=Path('artifacts')
out.mkdir()
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
with zipfile.ZipFile(out/'Lucid-Games-Complete.zip','w',allowZip64=True) as z:
    z.write(root/'README.md','README.md')
    z.write(root/'catalog.json','Lucid Content/catalog.json')
    for g in catalog['modules']:
        tmp=Path('module.tmp')
        fetch(g['url'],tmp,g,True)
        z.write(tmp,'Lucid Content/'+g['id']+'-'+g['version']+'.lgm')
        tmp.unlink()
    for f in pins['desktop']:
        tmp=Path(f['name'])
        fetch('/download/'+f['platform'],tmp,f)
        z.write(tmp,dirs[f['platform']]+'/'+f['name'])
        tmp.unlink()
source=out/'Lucid-Games-Launcher-Source.zip'
checks[source.name]=fetch('/download/source',source,pins['source'])
subprocess.run(['python3',str(source),'--verify'],check=True)
bundle=out/'Lucid-Games-Complete.zip'
with bundle.open('rb') as stream:checks[bundle.name]=hashlib.file_digest(stream,'sha256').hexdigest()
(out/'SHA256SUMS.txt').write_text(''.join(h+'  '+n+'\n' for n,h in checks.items()))
