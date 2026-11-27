"""Update one game's standalone engine, launcher module, complete collection and source ZIP.

Uses only the Python standard library. Outputs are valid seekable ZIPs. --materialize
writes ordinary single-file ZIPs for uploads. Large unchanged records can otherwise
be hashed/streamed directly from the previous official archives.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

from virtualzip import compose, VirtualPath

SLUG = 'galactic-realms'
LIBFILE = 'Lucid-Games-Launcher-Source.zip'
BUNDLE = 'Lucid-Games-Complete.zip'
ENGINE = 'engines/' + SLUG + '/'
SITE = 'games/' + SLUG + '/'
HUB = 'lucid-game-launcher/'
HUBCAT = HUB+'src/modules.json'
GHCAT = 'public-distribution/lucid-games/catalog.json'
BLOCK = 1024 * 1024
COMPRESSED = {'.xz','.zip','.gz','.png','.webp','.woff','.woff2','.jpg','.jpeg','.ico','.icns','.mp3','.mp4','.lgm','.jar','.flac','.ogg'}
OLD_SOURCE_SHA = 'c7151e933cb8ce179a8b140bb0af3d4ecc01ed4fd73707babe4574639c97a548'
OLD_COMPLETE_SHA = '0aa44f58a0dd58425326018208adbf4aa7f772aa9cfc2a69057baa978cf089a4'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode()


def compact(data):
    return json.dumps(data, separators=(',',':'), ensure_ascii=False)


def safe(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or name in ('.','..') or p.as_posix()!=name or '..' in p.parts or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError("Unsafe path: " + repr(name))
    return name


def info(name, size=0, stored=False):
    i = ZipInfo(safe(name), (2026,1,1,0,0,0))
    i.create_system=3
    i.external_attr=(stat.S_IFREG|0o644)<<16
    i.compress_type=ZIP_STORED if stored else ZIP_DEFLATED
    i.file_size=size
    i._compresslevel=6
    return i


def file_hash(file):
    with Path(file).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def check_source_base(args):
    inputs = [(args.source, args.old_source_sha)]
    if args.phase in ('bundle', 'all'):
        inputs.append((args.bundle, args.old_bundle_sha))
    for p, sha in inputs:
        marker = args.out/(p.name+'.baseline.json')
        st=p.stat()
        tag = [str(p.resolve()), st.st_size, st.st_mtime_ns, sha]
        if marker.is_file() and json.loads(marker.read_text()) == tag:
            continue
        if file_hash(p)!=sha:
            raise ValueError('Base archive changed: '+p.name)
        marker.write_text(json.dumps(tag))


def source_bytes(old, index, path):
    return old.read('objects/'+index['files'][path][0])


def read_rows(catalog):
    rows=[r for r in catalog['modules'] if r['id']==SLUG]
    if len(rows)!=1 or len(catalog['modules'])!=11:
        raise ValueError('Wrong launcher catalog')
    return rows[0]


def release_inputs(args, baseline_zip, index):
    raw=source_bytes(baseline_zip,index,HUBCAT)
    if raw!=source_bytes(baseline_zip,index,GHCAT) or len(index['games'])!=11:
        raise ValueError('Unexpected catalog or game roster')
    catalog=json.loads(raw)
    oldrow=read_rows(catalog)
    oldmod=index['modules'][SLUG]
    if oldrow['version']!=oldmod['version'] or oldrow['sha256']!=oldmod['sha256'] or oldrow['kind']!='static':
        raise ValueError('Wrong prior module')
    public=args.game_public
    if public.name=='game' and (public/'engine.json').exists():
        public=public.parent
    game=public/'game'
    engine=json.loads((game/'engine.json').read_text())
    if engine['version']!=args.version or engine['version']==oldrow['version']:
        raise ValueError('New engine has wrong version')
    checksum=hashlib.sha256()
    for n in engine['parts']:
        if safe(n)!=Path(n).name:
            raise ValueError('Invalid engine part: '+n)
        with (game/n).open('rb') as f:
            while block:=f.read(BLOCK):checksum.update(block)
    if checksum.hexdigest()!=engine['sha256'] or sum((game/n).stat().st_size for n in engine['parts'])!=engine['size']:
        raise ValueError('New engine parts differ from their manifest')
    entries={}
    for head,sha in oldmod['entries']:
        n=json.loads(head)['path']
        if not n.startswith('game/') and n not in ('i18n.mjs','portal-catalogue.mjs'):
            entries[n]=baseline_zip.read('objects/'+sha)
    # Keep the offline HTML wrapper and the exact published website helpers.
    # Current hosted source also carries the latest launcher revision and storage bridges.
    prefix=SITE+'public/'
    for key in index['files']:
        if key.startswith(prefix):
            n=key[len(prefix):]
            if ((n.startswith('game/') and not re.search(r'\.wasm\.gz\.part\d+$',n)) or n in ('i18n.mjs','portal-catalogue.mjs')):
                entries[n]=source_bytes(baseline_zip,index,key)
    for p in game.rglob('*'):
        if p.is_file():
            n=p.relative_to(public).as_posix()
            if re.search(r'\.wasm\.gz\.part\d+$',n) and n[5:] not in engine['parts']:
                continue
            entries[n]=p
    for n in ('i18n.mjs','portal-catalogue.mjs'):
        if (public/n).is_file():
            entries[n]=public/n
    for n in engine['parts']:assert 'game/'+n in entries
    assert set(('index.html','i18n.mjs','portal-catalogue.mjs','game/index.html')).issubset(entries)
    return public, engine, entries, catalog, oldmod


def build_module(args, source_zip, index):
    public,engine,entries,catalog,oldmod=release_inputs(args,source_zip,index)
    slug_version=SLUG+'-'+args.version+'.lgm'
    output=args.out/slug_version
    temporary = tempfile.NamedTemporaryFile(prefix='module-', dir=args.out, delete=False)
    tmp = Path(temporary.name)
    records = []
    with temporary as target, gzip.GzipFile(filename='',fileobj=target,mode='wb',compresslevel=6,mtime=0) as gz:
        for name,data in sorted(entries.items()):
            safe(name)
            size=data.stat().st_size if isinstance(data,Path) else len(data)
            head=compact({'path':name,'size':size})
            encoded=head.encode()
            gz.write(struct.pack('>I',len(encoded)))
            gz.write(encoded)
            h=hashlib.sha256()
            with (data.open('rb') if isinstance(data,Path) else io.BytesIO(data)) as f:
                while block:=f.read(BLOCK):
                    gz.write(block)
                    h.update(block)
            records.append([head,h.hexdigest()])
        gz.write(b'\x00\x00\x00\x00')
    tmp.replace(output)
    row=read_rows(catalog)
    row.update(version=args.version,url='/api/launcher/modules/'+SLUG+'/'+args.version,
               sha256=file_hash(output),bytes=output.stat().st_size)
    built={'file':slug_version,'version':args.version,'sha256':row['sha256'],'bytes':row['bytes'],'entries':records}
    (args.out/'module-record.json').write_bytes(json_bytes(row))
    (args.out/'catalog.json').write_bytes(json_bytes(catalog))
    (args.out/'module-entries.json').write_bytes(json_bytes(built))
    return output,built,catalog,entries


def bundle_stage(args, module_file, prior_module, catalog):
    delta=args.out/'bundle-changes.zip'
    catalog_name='Lucid Content/catalog.json'
    old_name='Lucid Content/'+prior_module['file']
    new_name='Lucid Content/'+module_file.name
    members=[]
    with ZipFile(args.bundle) as old:
        old_catalog=json.loads(old.read(catalog_name))
        if any(b!=a for a,b in zip(catalog['modules'],old_catalog['modules']) if a['id']!=SLUG) or (len(catalog['modules'])!=len(old_catalog['modules'])):
            raise ValueError('Unexpected changes to another bundled game')
        if old_name not in old.namelist():raise ValueError('Previous module missing')
        with ZipFile(delta,'w') as adds:
            raw=json_bytes(catalog)
            adds.writestr(info(catalog_name,len(raw),True),raw)
            with module_file.open('rb') as source,adds.open(info(new_name,module_file.stat().st_size,True),'w') as dest:
                shutil.copyfileobj(source,dest,BLOCK)
        for name in old.namelist():
            if name==old_name:members.append((delta,new_name))
            elif name==catalog_name:members.append((delta,name))
            else:members.append((args.bundle,name))
    path=compose(args.out/(BUNDLE+'.layout.json'),members)
    with path.open() as stream,ZipFile(stream) as z,ZipFile(args.bundle) as old:
        if sum(k.endswith('.lgm') for k in z.namelist())!=11:raise ValueError('Incomplete game roster')
        for name in old.namelist():
            if name in (old_name,catalog_name):continue
            if (old.getinfo(name).CRC,old.getinfo(name).file_size)!=(z.getinfo(name).CRC,z.getinfo(name).file_size):
                raise ValueError('Unrelated bundle member changed: '+name)
        if z.read(catalog_name)!=json_bytes(catalog):raise ValueError('Incorrect bundle catalog')
        with z.open(new_name) as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=read_rows(catalog)['sha256']:raise ValueError('Incorrect bundle module')
    return path

class Objects:
    def __init__(self, previous, changes):
        self.previous = previous
        self.changes = changes
        self.retained = {x.filename.split('/')[1] for x in previous.infolist() if x.filename.startswith('objects/')}
        self.added = set()

    def add(self, stream, name):
        sha=hashlib.file_digest(stream, 'sha256').hexdigest()
        if sha not in self.retained and sha not in self.added:
            stream.seek(0)
            stored = Path(name).suffix.lower() in COMPRESSED or re.search(r'\.(?:gz|zip)\.part\d+$',name)
            with self.changes.open(info('objects/'+sha,stored=bool(stored)),'w') as target:
                shutil.copyfileobj(stream,target,BLOCK)
            self.added.add(sha)
        return sha

    def record(self, files, dest, contents, mode=0o644):
        with (contents.open('rb') if isinstance(contents,Path) else io.BytesIO(contents)) as stream:
            files[safe(dest)]=[self.add(stream,dest),0o755 if mode&0o111 else 0o644]


def keep(path):
    """Select editable source files from the hosted game or launcher repository."""
    p = PurePosixPath(path)
    skipped = {'.git','node_modules','__pycache__','.sites-runtime','desktop-releases','portable-build',
               '.electron-cache','.dart_tool','.gradle','.kotlin','.idea','Pods','xcuserdata',
               'DerivedData','ephemeral','.symlinks','.plugin_symlinks','.sites-checkout'}
    if skipped.intersection(p.parts):
        return False
    if path.startswith('public/releases/') and p.name != 'manifest.json':
        return False
    if path.startswith(('handoff/history/','docs/history/','build/cache/')):
        return False
    if path.startswith('assets/seed/') and p.suffix == '.bin':
        return False
    if p.suffix.lower() in {'.log','.pyc','.tsbuildinfo','.iml','.keystore','.jks','.p12','.mobileprovision'}:
        return False
    if p.name.lower() in {'local.properties','key.properties','keystore.properties','generated.xcconfig',
                          'flutter_export_environment.sh','.flutter-plugins-dependencies','.ds_store'}:
        return False
    if p.name.startswith('.env'):
        return p.name in ('.env.sample','.env.example')
    if path.startswith(('docs/','handoff/','portable/','packaging/')) and p.suffix.lower() in {'.md','.txt','.json','.xlsx','.csv','.png','.jpg'}:
        if re.search(r'(?:^|[-_.])(validation|verification|audit|review|test-result|benchmark-result)(?:[-_.]|$)',p.name.lower()):
            return False
        return p.name.lower() not in {'current-source-comparison.json','current-transfer-result.json','startup-fix-web-build.json'}
    return True


class ChecksumSink:
    def __init__(self):
        self.hash = hashlib.sha256()
        self.bytes = 0

    def write(self, data):
        self.hash.update(data)
        self.bytes += len(data)
        return len(data)

    def flush(self):
        pass


def verify_source(path):
    with path.open() as stream, ZipFile(stream) as z:
        manifest = json.loads(z.read('source-index.json'))
        if manifest['schema'] != 2 or len(manifest['games']) != 11 or set(manifest['modules']) != set(manifest['games']):
            raise ValueError('Invalid integrated source inventory')
        referenced = set()
        for filename, (sha, mode) in manifest['files'].items():
            safe(filename)
            if mode not in (0o644, 0o755):
                raise ValueError('Invalid mode: '+filename)
            referenced.add(sha)
        for module in manifest['modules'].values():
            names = set()
            target = ChecksumSink()
            with gzip.GzipFile(filename='', fileobj=target, mode='wb', compresslevel=6, mtime=0) as gz:
                for header, sha in module['entries']:
                    meta = json.loads(header)
                    name = safe(meta['path'])
                    if name in names or meta['size'] != z.getinfo('objects/'+sha).file_size:
                        raise ValueError('Invalid module metadata: '+name)
                    names.add(name)
                    referenced.add(sha)
                    raw = header.encode()
                    gz.write(struct.pack('>I',len(raw)))
                    gz.write(raw)
                    with z.open('objects/'+sha) as src:
                        shutil.copyfileobj(src,gz,BLOCK)
                gz.write(b'\x00\x00\x00\x00')
            if target.hash.hexdigest() != module['sha256'] or target.bytes != module['bytes']:
                raise ValueError('Cannot reproduce published game module: '+module['file'])
        expected = {'objects/'+sha for sha in referenced} | {'source-index.json','START-HERE.ko.md','__main__.py'}
        if len(z.namelist()) != len(expected) or set(z.namelist()) != expected:
            raise ValueError('Missing or unexpected archive members')
        for sha in referenced:
            if not re.fullmatch('[0-9a-f]{64}',sha):
                raise ValueError('Invalid source object ID')
            with z.open('objects/'+sha) as f:
                if hashlib.file_digest(f,'sha256').hexdigest() != sha:
                    raise ValueError('Corrupt source object: '+sha)
        for name, sha in manifest['entrypoints'].items():
            if digest(z.read(safe(name))) != sha:
                raise ValueError('Corrupt development entry point: '+name)


def sync_repo(objects, files, root, old_ref, new_ref, prefix):
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args])
    if not new_ref or not re.fullmatch('[0-9a-f]{40}',new_ref):raise ValueError('Missing published Git commit: '+prefix)
    if git('rev-parse',new_ref+'^{commit}').decode().strip()!=new_ref:
        raise ValueError('Git commit unavailable: '+new_ref)
    paths=git('diff','--no-renames','--name-only','-z',old_ref,new_ref).decode().split('\0')
    for name in filter(None,paths):
        safe(name)
        if not keep(name):continue
        p=prefix+name
        entry=git('ls-tree','-z',new_ref,'--',name)
        if not entry:
            files.pop(p,None)
            continue
        tree,actual=entry[:-1].split(b'\t',1)
        mode,kind,oid=tree.decode().split()
        if actual.decode()!=name:raise ValueError('Git tree mismatch')
        if mode not in ('100644','100755') or kind!='blob':
            if p in files:raise ValueError('Managed source became non-regular: '+p)
            continue
        # Large desktop ZIP parts are separate downloadable outputs and were filtered by the original packaging.
        raw=git('cat-file','blob',oid)
        objects.record(files,p,raw,int(mode,8))


def source_stage(args, source_zip, baseline, built,catalog, entries):
    delta=args.out/'source-changes.zip'
    final=deepcopy(baseline)
    f=final['files']
    public=args.game_public
    if public.name=='game' and (public/'engine.json').is_file():public=public.parent
    if not args.new_source.is_file():raise FileNotFoundError(args.new_source)
    with ZipFile(delta,'w',allowZip64=True) as patches:
        obj=Objects(source_zip,patches)
        with ZipFile(args.new_source) as native:
            members=native.infolist()
            stem='galactic-'+args.version+'-source/'
            if not members or any(not m.filename.startswith(stem) for m in members):raise ValueError('Not the new standalone engine archive')
            if native.read(stem+'VERSION').decode().strip()!=args.version:raise ValueError('Incorrect game source release')
            old_engine={key for key in f if key.startswith(ENGINE)}
            new_engine=set()
            for member in members:
                rel=member.filename[len(stem):]
                if not rel or member.is_dir():continue
                key=ENGINE+safe(rel)
                if key in new_engine:raise ValueError('Duplicate engine member '+key)
                new_engine.add(key)
                with native.open(member) as stream:
                    sha=obj.add(stream,rel)
                f[key]=[sha,0o755 if (member.external_attr>>16)&0o111 else 0o644]
            for key in old_engine-new_engine:del f[key]
        if args.site_tree:
            sync_repo(obj,f,args.site_tree,baseline['games'][SLUG]['siteCommit'],args.site_commit,SITE)
        else:
            for key in list(f):
                if key.startswith(SITE+'public/game/') and re.search(r'\.wasm\.gz\.part\d+$',key):
                    del f[key]
            for n,data in entries.items():
                if n=='index.html':continue
                obj.record(f,SITE+'public/'+n,data)
            obj.record(f,SITE+'public/releases/manifest.json',public/'releases/manifest.json')
        if args.hub_tree:
            sync_repo(obj,f,args.hub_tree,baseline['hubCommit'],args.hub_commit,HUB)
        catalog_bytes=json_bytes(catalog)
        if args.hub_tree and f[HUBCAT][0]!=digest(catalog_bytes):
            raise ValueError('The published launcher catalog differs from the updated module')
        for key in (HUBCAT,GHCAT):obj.record(f,key,catalog_bytes)
        for (head,sha),(name,content) in zip(built['entries'],sorted(entries.items())):
            assert json.loads(head)['path']==name
            with (content.open('rb') if isinstance(content,Path) else io.BytesIO(content)) as stream:
                if obj.add(stream,name)!=sha:raise ValueError('Module source changed while packaging')
            if name.startswith('game/') and f[SITE+'public/'+name][0]!=sha:
                raise ValueError('Launcher bytes differ from final hosted source: '+name)
        manifest=json.loads((public/'releases/manifest.json').read_bytes())
        if manifest['version']!=args.version or f[SITE+'public/releases/manifest.json'][0]!=file_hash(public/'releases/manifest.json'):
            raise ValueError('Wrong native release manifest in integrated sources')
        final['modules'][SLUG]=built
        if args.site_commit and not re.fullmatch(r'[0-9a-f]{40}',args.site_commit):raise ValueError('Invalid game commit')
        if args.hub_commit and not re.fullmatch(r'[0-9a-f]{40}',args.hub_commit):raise ValueError('Invalid launcher commit')
        if args.site_commit:
            final['games'][SLUG]={'siteCommit':args.site_commit}
        else:
            final['games'][SLUG]={'siteCommit':'unpublished','basedOn':baseline['games'][SLUG]['siteCommit']}
        if args.hub_commit:
            final['hubCommit']=args.hub_commit
        else:
            final['hubCommit']='unpublished'
            final['hubBasedOn']=baseline['hubCommit']
        raw=(json.dumps(final,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
        patches.writestr(info('source-index.json'),raw)
    targets={rec[0] for rec in f.values()}
    for mod in final['modules'].values():
        targets.update(sha for head,sha in mod['entries'])
    order=[]
    for item in source_zip.infolist():
        name=item.filename
        if name.startswith('objects/') and name.partition('/')[2] in targets:
            order.append((args.source,name))
    with ZipFile(delta) as changes:
        for name in changes.namelist():
            if name.startswith('objects/') and name.partition('/')[2] in targets:
                order.append((delta,name))
    order.extend([(args.source,'__main__.py'),(args.source,'START-HERE.ko.md'),(delta,'source-index.json')])
    path=compose(args.out/(LIBFILE+'.layout.json'),order)
    verify_source(path)
    for k in baseline:
        if k not in ('files','modules','games','hubCommit') and final[k]!=baseline[k]:
            raise ValueError('Unrelated top-level source record changed: '+k)
    for slug in baseline['modules']:
        if slug!=SLUG and (final['modules'][slug]!=baseline['modules'][slug] or baseline['games'][slug]!=final['games'][slug]):
            raise ValueError('Changed another game: '+slug)
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['module','bundle','source','all'])
    p.add_argument('--version',default='2.5.2')
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--bundle',type=Path,help='Previous official complete collection ZIP, required for bundle or all')
    p.add_argument('--new-source',type=Path)
    p.add_argument('--game-public',type=Path,required=True)
    p.add_argument('--site-tree',type=Path)
    p.add_argument('--site-commit')
    p.add_argument('--hub-tree',type=Path)
    p.add_argument('--hub-commit')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--old-source-sha',default=OLD_SOURCE_SHA)
    p.add_argument('--old-bundle-sha',default=OLD_COMPLETE_SHA)
    p.add_argument('--materialize',action='store_true')
    args=p.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version):p.error('Invalid game version')
    if args.phase in ('bundle','all') and not args.bundle:p.error('Previous complete collection ZIP is required')
    if args.phase in ('source','all') and not args.new_source:p.error('Final game source ZIP is required')
    args.out=args.out.resolve()
    args.out.mkdir(parents=True,exist_ok=True)
    check_source_base(args)
    with ZipFile(args.source) as old:
        baseline=json.loads(old.read('source-index.json'))
        module_file,built,catalog,entries=build_module(args,old,baseline)
        row=read_rows(catalog)
        print('Module',row['version'],row['bytes'],row['sha256'],flush=True)
        legs=[]
        if args.phase in ('bundle','all'):
            legs.append(bundle_stage(args,module_file,baseline['modules'][SLUG],catalog))
        if args.phase in ('source','all'):
            legs.append(source_stage(args,old,baseline,built,catalog,entries))
    for part in legs:
        key='source' if part.name==LIBFILE else 'bundle'
        meta={'name':part.name,'bytes':part.stat().st_size,'sha256':part.checksum()}
        if args.materialize:
            part.materialize(args.out/part.name)
            if file_hash(args.out/part.name)!=meta['sha256']:raise ValueError('Incorrect materialized ZIP')
        (args.out/(key+'-result.json')).write_bytes(json_bytes(meta))
        print(meta,flush=True)


if __name__=='__main__':
    main()
