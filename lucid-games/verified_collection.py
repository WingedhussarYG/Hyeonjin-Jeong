"""Publish a previously verified integrated collection, preserving its offline bytes."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def check_file(path, pin):
    with path.open("rb") as inp:
        actual = digest(inp)
    if actual != pin["sha256"] or path.stat().st_size != pin["bytes"]:
        raise ValueError(f"Unexpected contents for {path.name}")


def get_verified_job(repo, run, destination):
    number = int(run["id"])
    info = json.loads(subprocess.check_output(["gh", "api", f"repos/{repo}/actions/runs/{number}"]))
    if (info["head_sha"], info["conclusion"], info["head_repository"]["full_name"]) != (run["sha"], "success", repo):
        raise ValueError("The candidate verification run did not pass in this repository")
    subprocess.run(["gh", "run", "download", str(number), "--repo", repo,
                    "--name", run["artifact"], "--dir", str(destination)], check=True)


def check_member(bundle, member, pin):
    with bundle.open(member) as inp:
        actual = digest(inp)
    if actual != pin["sha256"] or bundle.getinfo(member).file_size != pin["bytes"]:
        raise ValueError(f"Unexpected bundled file {member}")


def publish_verified(root, output, pins, candidate):
    repo = os.environ["GITHUB_REPOSITORY"]
    catalog_bytes = (root / "catalog.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    version = candidate["gameVersion"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid game version")
    platforms = {"windows-x64":"Windows", "linux-x64":"Linux",
                 "macos-arm64":"macOS-Apple-Silicon", "macos-x64":"macOS-Intel"}
    if len(catalog["modules"]) != 11 or set(platforms) != {p["platform"] for p in pins["desktop"]}:
        raise ValueError("Incomplete release catalog")
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        sandbox = Path(temp)
        packed = sandbox / "integrated"
        standalone = sandbox / "game"
        get_verified_job(repo, candidate["collection"], packed)
        get_verified_job(repo, candidate["game"], standalone)
        if (packed / "catalog.json").read_bytes() != catalog_bytes:
            raise ValueError("Repository and downloadable catalogs differ")
        source = packed / "Lucid-Games-Launcher-Source.zip"
        combined = packed / "Lucid-Games-Complete.zip"
        check_file(source, pins["source"])
        check_file(combined, {"sha256":pins["bundleSha256"], "bytes":pins["bundleBytes"]})
        # The development archive's verifier needs only its local Python runtime.
        env = {"PATH":os.environ["PATH"], "LANG":"C.UTF-8"}
        subprocess.run([sys.executable, str(source), "--verify"], check=True, env=env)
        with zipfile.ZipFile(combined) as archive:
            if archive.read("Lucid Content/catalog.json") != catalog_bytes or archive.read("README.md") != (root/"README.md").read_bytes():
                raise ValueError("Bundled documentation or catalog mismatch")
            members = {"README.md","Lucid Content/catalog.json"}
            for row in catalog["modules"]:
                key = "Lucid Content/"+row["id"]+"-"+row["version"]+".lgm"
                check_member(archive,key,row)
                members.add(key)
            for item in pins["desktop"]:
                key = platforms[item["platform"]]+"/"+item["name"]
                check_member(archive,key,item)
                members.add(key)
            if set(archive.namelist()) != members or len(archive.namelist()) != len(members):
                raise ValueError("Unexpected files in the offline bundle")
        os.replace(source,output/source.name)
        os.replace(combined,output/combined.name)
        module=next(row for row in catalog["modules"] if row["id"]=="galactic-realms")
        if module["version"]!=version:
            raise ValueError("Wrong integrated game version")
        module_file=packed/f"galactic-realms-{version}.lgm"
        check_file(module_file,module)
        os.replace(module_file,output/module_file.name)
        archive_names={f"galactic-{version}-{flavor}.zip" for flavor in ("source","windows-x64","macos-universal","linux-x64")}
        hashes={}
        for line in (standalone/f"galactic-{version}-checksums.txt").read_text().splitlines():
            h,item=line.split()
            if not re.fullmatch(r"[0-9a-f]{64}",h) or Path(item).name!=item:
                raise ValueError("Invalid game checksum record")
            hashes[item]=h
        for name in sorted(archive_names):
            p=standalone/name
            with p.open("rb") as inp:
                if digest(inp)!=hashes[name]:
                    raise ValueError("Wrong standalone release: "+name)
            os.replace(p,output/p.name)
        for item in pins["mobile"]:
            # These apps ship the nine mobile games. The two desktop RTS games are separate.
            p=output/item["name"]
            subprocess.run(["gh","release","download",candidate["baseTag"],"--repo",repo,
                            "--pattern",p.name,"--dir",str(output)],check=True)
            check_file(p,item)
    checks=[]
    for p in sorted(output.iterdir()):
        if p.is_file() and p.name!="SHA256SUMS.txt":
            with p.open("rb") as inp:
                checks.append(digest(inp)+"  "+p.name+"\n")
    (output/"SHA256SUMS.txt").write_text("".join(checks))
