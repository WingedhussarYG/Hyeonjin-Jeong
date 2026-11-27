"""Refresh the launcher tree inside a verified Lucid Games source archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def safe(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or path.as_posix() != name or ".." in path.parts:
        raise ValueError(f"Unsafe archive path: {name!r}")
    return name


def object_name(digest: str) -> str:
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Invalid object digest")
    return "objects/" + digest


def zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = ZIP_DEFLATED
    info._compresslevel = 6
    return info


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def add_file(archive: ZipFile, index: dict, path: str, source: Path) -> None:
    path = safe(path)
    value = source.read_bytes()
    checksum = hashlib.sha256(value).hexdigest()
    key = object_name(checksum)
    if key not in archive.NameToInfo:
        archive.writestr(zip_info(key), value)
    mode = index["files"].get(path, [None, 0o644])[1]
    index["files"][path] = [checksum, mode]


def referenced_objects(index: dict) -> set[str]:
    objects = {object_name(value[0]) for value in index["files"].values()}
    for module in index["modules"].values():
        objects.update(object_name(checksum) for _, checksum in module["entries"])
    return objects


def refresh(base: Path, output: Path, root: Path) -> None:
    patch_root = root / "source-patch"
    manifest = json.loads((patch_root / "patch.json").read_text())
    if output.exists():
        raise FileExistsError(output)
    shutil.copyfile(base, output)
    with ZipFile(output, "a", allowZip64=True) as archive:
        index = json.loads(archive.read("source-index.json"))
        if index["hubCommit"] not in manifest["baseLauncherCommits"]:
            raise ValueError("The base archive contains a different launcher commit")
        tail = archive.getinfo("source-index.json")
        if archive.filelist[-1] is not tail:
            raise ValueError("The source index is not the final archive member")
        archive.filelist.pop()
        del archive.NameToInfo[tail.filename]
        archive.start_dir = tail.header_offset

        overlays = {"lucid-game-launcher": manifest["launcherFiles"]}
        game = manifest.get("gameSite")
        if game:
            slug = safe(game["slug"])
            game_record = index["games"][slug]
            if game_record.get("basedOn") != game["baseCommit"] or game_record.get("siteCommit") != "unpublished":
                raise ValueError("The archived game site does not match the release being promoted")
            overlays["games/" + slug] = game["files"]
            if index["files"]["lucid-game-launcher/src/modules.json"][0] != digest(root / "catalog.json"):
                raise ValueError("The archived and published launcher catalogs differ")
            game_record["siteCommit"] = game["commit"]
            index["hubBasedOn"] = manifest["previousLiveLauncherCommit"]
        for prefix, changes in overlays.items():
            for item in changes:
                destination = prefix + "/" + safe(item["path"])
                source = patch_root / destination
                if digest(source) != item["sha256"] or index["files"].get(destination, [None])[0] != item["baseSha256"]:
                    raise ValueError("Source patch digest mismatch: " + destination)
                add_file(archive, index, destination, source)

        public_files = [
            "README.md",
            "catalog.json",
            "publish.py",
            "verified_collection.py",
            "refresh_source.py",
        ]
        if game:
            public_files.append("updates/galactic-2.5.2.md")
        for name in public_files:
            add_file(archive, index, "public-distribution/lucid-games/" + name, root / name)
        add_file(
            archive,
            index,
            "public-distribution/.github/workflows/publish-lucid-games.yml",
            root.parent / ".github/workflows/publish-lucid-games.yml",
        )
        for source in sorted(patch_root.rglob("*")):
            if source.is_file():
                relative = source.relative_to(root).as_posix()
                add_file(archive, index, "public-distribution/lucid-games/" + relative, source)

        index["hubCommit"] = manifest["launcherCommit"]
        keep = referenced_objects(index)
        for info in list(archive.filelist):
            if info.filename.startswith("objects/") and info.filename not in keep:
                archive.filelist.remove(info)
                del archive.NameToInfo[info.filename]
        archive.writestr(
            zip_info("source-index.json"),
            (json.dumps(index, separators=(",", ":"), ensure_ascii=False, sort_keys=True) + "\n").encode(),
        )

    subprocess.run([sys.executable, str(output), "--verify"], check=True)
    print(json.dumps({"bytes": output.stat().st_size, "sha256": digest(output)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    refresh(args.base, args.output, args.root)


if __name__ == "__main__":
    main()
