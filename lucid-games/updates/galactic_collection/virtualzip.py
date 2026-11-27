"""Compose a byte-exact ZIP from immutable local member records without copying large members."""
from __future__ import annotations
import bisect
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile


class _DirectoryTail(io.BytesIO):
    def __init__(self, prefix_size):
        super().__init__()
        self.prefix_size = prefix_size

    def tell(self):
        return self.prefix_size + super().tell()

    def seek(self, offset, whence=os.SEEK_SET):
        if whence == os.SEEK_SET:
            if offset < self.prefix_size:
                raise ValueError("Access to an immutable ZIP prefix")
            offset -= self.prefix_size
        return self.prefix_size + super().seek(offset, whence)


def compose(layout_path, members):
    """Each (zip_path, name) denotes an existing, validated local ZIP member."""
    layout_path = Path(layout_path).resolve()
    paths = list(dict.fromkeys(Path(p).resolve() for p, _ in members))
    spans = []
    offset = 0
    records = []
    seen = set()
    from contextlib import ExitStack
    with ExitStack() as stack:
        inputs = {p: stack.enter_context(ZipFile(p)) for p in paths}
        ranges = {}
        for path, z in inputs.items():
            values = sorted(z.infolist(), key=lambda value: value.header_offset)
            if len(values) != len(set(x.filename for x in values)):
                raise ValueError("Duplicate input entry: " + str(path))
            following = [x.header_offset for x in values[1:]] + [z.start_dir]
            ranges[path] = {x.filename:(x.header_offset,end-x.header_offset) for x,end in zip(values,following)}
        for p, name in members:
            path = Path(p).resolve()
            if name in seen:
                raise ValueError("Duplicate output entry: " + name)
            seen.add(name)
            info = copy.copy(inputs[path].getinfo(name))
            start, length = ranges[path][name]
            if info.flag_bits & 9 or length < 30 + info.compress_size:
                raise ValueError("Unexpected local ZIP record: " + name)
            info.header_offset = offset
            records.append(info)
            if spans and spans[-1][0] == str(path) and spans[-1][1] + spans[-1][2] == start:
                spans[-1][2] += length
            else:
                spans.append([str(path), start, length])
            offset += length
    tail = _DirectoryTail(offset)
    with ZipFile(tail, 'w', allowZip64=True) as out:
        out.filelist.extend(records)
        out.NameToInfo.update((r.filename, r) for r in records)
    tail_path = layout_path.with_suffix('.central')
    footer = tail.getvalue()
    tail_path.write_bytes(footer)
    spans.append([str(tail_path), 0, len(footer)])
    total = offset + len(footer)
    meta = {'format':1,'length':total,'name':layout_path.name.replace('.layout.json',''),'parts':spans}
    temp = layout_path.with_suffix('.tmp')
    temp.write_text(json.dumps(meta,separators=(',',':')))
    temp.replace(layout_path)
    return VirtualPath(layout_path)


class ExtentStream(io.RawIOBase):
    def __init__(self, parts, length):
        super().__init__()
        self.parts = parts
        self.length = length
        self.position = 0
        self.ends = []
        self.handles = {}
        end = 0
        for name, start, length in parts:
            if start < 0 or length <= 0:
                raise ValueError("Invalid archive extent")
            end += length
            self.ends.append(end)
        if end != self.length:
            raise ValueError("Archive size mismatch")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=os.SEEK_SET):
        if whence == os.SEEK_CUR:
            offset += self.position
        elif whence == os.SEEK_END:
            offset += self.length
        elif whence != os.SEEK_SET:
            raise ValueError("Invalid seek origin")
        if offset < 0:
            raise ValueError("Negative seek")
        self.position = offset
        return offset

    def readinto(self, target):
        if self.closed:
            raise OSError("Archive closed")
        view = memoryview(target)
        count = min(len(view), max(0, self.length - self.position))
        copied = 0
        while copied < count:
            index = bisect.bisect_right(self.ends, self.position)
            name, start, length = self.parts[index]
            within = self.position - (self.ends[index] - length)
            n = min(count - copied, length - within)
            fd = self.handles.get(name)
            if fd is None:
                fd = open(name,'rb',buffering=0)
                self.handles[name] = fd
            fd.seek(start + within)
            if fd.readinto(view[copied:copied+n]) != n:
                raise EOFError("Truncated archive input: " + name)
            self.position += n
            copied += n
        return copied

    def close(self):
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()
        super().close()


class VirtualPath:
    """Path-like open/stat subset for the launcher's existing multipart publisher."""
    def __init__(self, index):
        self.index = Path(index).resolve()
        data = json.loads(self.index.read_text())
        if data['format'] != 1:
            raise ValueError("Unknown archive layout")
        self.name = data['name']
        self.size = data['length']
        self.parts = data['parts']

    def open(self, mode='rb'):
        if mode != 'rb':
            raise ValueError("Read-only virtual ZIP")
        return io.BufferedReader(ExtentStream(self.parts, self.size),1<<20)

    def stat(self):
        return SimpleNamespace(st_size=self.size)

    def checksum(self):
        with self.open() as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()

    def materialize(self, target):
        import shutil
        dest = Path(target)
        with self.open() as source, dest.open('xb') as output:
            shutil.copyfileobj(source,output,1<<20)
