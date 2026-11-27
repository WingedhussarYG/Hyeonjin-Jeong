"""Restore the pinned project snapshot, build the desktop distribution and write the release assets."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64,gzip,hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile,zipfile
HERE=Path(__file__).resolve().parent
BASE='https://lucid-writer.maxfaine.chatgpt.site'
EXE='/studio/releases/Lucid-Studio-1.0.0-windows-x64-portable.exe'
HASH='503dd8f84533fb1b1c921250f0c6dcacb1d598da1a99bc9bca0a98c0baf4610f'
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def download(url,dest,expected):
 subprocess.run(['curl','--fail','--location','--silent','--show-error','--retry','3',url,'-o',str(dest)],check=True)
 if sha(dest)!=expected:raise ValueError('Upstream file failed verification: '+url)
def pack_locale(directory):
 files={}
 for rel,target in [('program/resource','program/resource'),('share/.registry','share/registry')]:
  for f in sorted((directory/rel).rglob('*')):
   if f.is_file() and f.suffix in ('.mo','.xcd'):files['/instdir/'+target+'/'+f.relative_to(directory/rel).as_posix()]=base64.b64encode(f.read_bytes()).decode()
 return gzip.compress(json.dumps(files,sort_keys=True,separators=(',',':')).encode(),mtime=0)
def pack_zip(root,dest,folder):
 with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True,strict_timestamps=False) as z:
  for f in sorted(root.rglob('*')):
   if f.is_file():z.write(f,folder+'/'+str(f.relative_to(root)))
def portable_payload(original, work):
    """Extract the verified 7-Zip payload from the NSIS portable wrapper."""
    payload = work/'portable.7z'
    with original.open('rb') as src, payload.open('wb') as out:
        src.seek(75560)
        remaining = 247564600
        while remaining:
            block = src.read(min(1024*1024, remaining))
            if not block:
                raise ValueError('Incomplete Windows portable payload.')
            out.write(block)
            remaining -= len(block)
    with payload.open('rb') as src:
        if hashlib.file_digest(src,'sha256').hexdigest()!='e730bc56cd2dd85c08522fb41e3e0e958a26dfe9c67ade9ac2c48910b1abb86d':
            raise ValueError('The embedded Windows portable payload failed verification.')
    return payload

def main():
 out=Path('artifacts').resolve();out.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as td:
  work=Path(td);root=work/'source';root.mkdir()
  original=work/'original.exe';download(BASE+EXE,original,HASH)
  desktop=work/'runtime'
  result=subprocess.run([shutil.which('7z') or shutil.which('7zz') or '7z','x','-t7z','-y','-o'+str(desktop),str(portable_payload(original,work))],stdout=subprocess.DEVNULL)
  if result.returncode not in (0,1):result.check_returncode()
  app=desktop/'resources/app';native=root/'native-app';shutil.copytree(app,native)
  suite_zip=work/'suite-original.zip'
  download('https://lucid-pixel.maxfaine.chatgpt.site/api/suite-downloads/Lucid-Suite-win32-x64-0.3.11.zip',suite_zip,'2e6bdb327eba6506ac42367f3734a07b09d6b2e6e2448752e7439a77e4ba6baa')
  with zipfile.ZipFile(suite_zip) as archive:
   prefix='Lucid-Suite/resources/app/'
   for name in archive.namelist():
    if name.startswith(prefix) and not name.endswith('/'):
     f=root/'standalone-suite-app'/name[len(prefix):];f.parent.mkdir(exist_ok=True,parents=True);f.write_bytes(archive.read(name))
  packdir=work/'packs';packdir.mkdir()
  for code,info in json.loads((HERE/'language-packs.json').read_text()).items():
   f=work/(code+'.deb');download(info['url'],f,info['sha256']);dst=work/code
   subprocess.run(['dpkg-deb','-x',str(f),str(dst)],check=True)
   (packdir/(code+'.json.gz')).write_bytes(pack_locale(dst/'usr/lib/libreoffice'))
  overlay=work/'overlay';overlay.mkdir()
  archive_path=work/'overlay.tar.gz'
  parts=sorted(HERE.glob('overlay.tar.gz.part*'))
  with archive_path.open('wb') as joined:
   for part in parts:
    with part.open('rb') as src:shutil.copyfileobj(src,joined)
  with tarfile.open(archive_path) as t:t.extractall(overlay,filter='data')
  engine=(desktop/'resources/office-engine/soffice.wasm').read_bytes()
  index=json.loads((HERE/'source-files.json').read_text())
  def restore(pair):
   path,row=pair;dest=root/path;dest.parent.mkdir(exist_ok=True,parents=True)
   if 'native' in row:shutil.copyfile(app/row['native'],dest)
   elif 'engine' in row:shutil.copyfile(desktop/'resources/office-engine'/row['engine'],dest)
   elif 'part' in row:
    part=row['part'];dest.write_bytes(engine[part*8388608:(part+1)*8388608])
   elif 'pack' in row:shutil.copyfile(packdir/row['pack'],dest)
   elif 'overlay' in row:shutil.copyfile(overlay/row['overlay'],dest)
   else:download(BASE+row['url'],dest,row['hash'])
   if sha(dest)!=row['hash'] and ('pack' not in row or hashlib.sha256(gzip.decompress(dest.read_bytes())).hexdigest()!=row['uncompressed_sha256']):raise ValueError('Source integrity mismatch: '+path)
   dest.chmod(row['mode'])
  with ThreadPoolExecutor(max_workers=6) as executor:list(executor.map(restore,index.items()))
  shutil.copy2(HERE/'package-studio-windows.py',root/'scripts/package-studio-windows.py')
  shutil.copy2(HERE/'locale.js',root/'localisation/locale.js')
  hints=[l.split('\t') for l in (HERE/'field-hints.tsv').read_text().splitlines()]
  for i,lang in enumerate(['ko','en-gb','de','fr','es','ja','zh-cn']):
   p=root/'localisation'/('strings-'+lang+'.json');d=json.loads(p.read_text());d.update({row[0]:row[i] for row in hints});p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')))
  for tree in [native,app]:
   subprocess.run([sys.executable,str(root/'localisation/apply.py'),'desktop',str(tree)],check=True)
  subprocess.run([sys.executable,str(root/'localisation/apply.py'),'suite',str(root/'standalone-suite-app')],check=True)
  shutil.copy2(root/'STUDIO-README.md',desktop/'README.md')
  source_zip=out/'Lucid-Studio-1.1.0-Source.zip';desktop_zip=out/'Lucid-Studio-1.1.0-Windows-x64.zip'
  pack_zip(desktop,desktop_zip,'Lucid Studio')
  wasm=root/'web/office/runtime/soffice.wasm'
  had_wasm=wasm.exists()
  subprocess.run([sys.executable,str(root/'scripts/build-studio-downloads.py'),str(out)],check=True)
  catalogue=root/'studio/web/studio/downloads.json'
  links=json.loads(catalogue.read_text())
  for record in json.loads((out/'web-editions.json').read_text())['files']:
   links['editions'][record['id']].update(size=record['size'],sha256=record['sha256'])
  catalogue.write_text(json.dumps(links,ensure_ascii=False,indent=2)+'\n')
  shutil.rmtree(root/'.sites-runtime')
  if not had_wasm:wasm.unlink(missing_ok=True)
  pack_zip(root,source_zip,'Lucid Studio Source')
  (out/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+f.name+'\n' for f in sorted(out.iterdir()) if f.is_file() and f.name!='SHA256SUMS.txt'))
if __name__=='__main__':main()
