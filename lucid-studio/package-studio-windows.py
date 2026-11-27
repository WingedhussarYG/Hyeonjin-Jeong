"""Make an offline Windows ZIP using the pinned Electron runtime and the editable Studio source."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = 'https://lucid-writer.maxfaine.chatgpt.site/studio/releases/Lucid-Studio-1.0.0-windows-x64-portable.exe'
DIGEST = '503dd8f84533fb1b1c921250f0c6dcacb1d598da1a99bc9bca0a98c0baf4610f'

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
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('output', type=Path)
    args.add_argument('--upstream', type=Path, help='Existing copy of the original 1.0.0 Windows executable.')
    args.add_argument('--sevenzip', default='7z')
    options = args.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        original = options.upstream or work/'original.exe'
        if not options.upstream:
            urllib.request.urlretrieve(ORIGINAL, original)
        with original.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=DIGEST:
                raise ValueError('The upstream Windows executable failed verification.')
        distribution = work/'Lucid Studio'
        result = subprocess.run([options.sevenzip,'x','-t7z','-y','-o'+str(distribution),str(portable_payload(original,work)),'-xr!app'])
        if result.returncode not in (0,1):
            result.check_returncode()
        for name in ('Lucid Studio.exe','resources/office-engine/soffice.wasm','resources/vendor/win32-x64/ffmpeg.exe'):
            if not (distribution/name).is_file():
                raise FileNotFoundError(name)
        app = distribution/'resources/app'
        shutil.copytree(ROOT/'native-app',app)
        subprocess.run([__import__('sys').executable,str(ROOT/'localisation/apply.py'),'desktop',str(app)],check=True)
        shutil.copy2(ROOT/'STUDIO-README.md',distribution/'README.md')
        options.output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(options.output,'w',ZIP_DEFLATED,compresslevel=5,strict_timestamps=False) as archive:
            for path in sorted(distribution.rglob('*')):
                if path.is_file(): archive.write(path,path.relative_to(work))

if __name__=='__main__':
    main()
