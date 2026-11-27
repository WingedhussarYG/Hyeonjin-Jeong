"""Build the selective Galactic Realms unit art rollback from the previous signed-off collection."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import zipfile

GAME = "galactic-realms"
OLD = "2.5.1"
NEW = "2.5.2"
OLD_ENGINE = "b88503933b05ae157e3cb660a1ace89a6601fd1f3c81d944b32f64a03ca15701"
PROTECTED = {
    "rae_executioner", "ter_thor", "ter_swannthor", "ter_blackhammer", "ter_odin",
    "ter_tychusodin", "ter_xanthos", "nod_redeemer", "scr_annihilator", "scr_reaper",
    "scr_hexapod", "pro_colossus", "pro_warbringer", "pro_wrathwalker", "pro_reaver",
    "pro_immortal", "pro_stalker", "pro_dragoon",
}
WEB_UPDATES = ("app/portal.tsx", "vite.config.ts", "launcher/gateway.mjs",
               "launcher/worker.ts", "launcher/upstream.json", "public/game/revision.mjs",
               "public/game/storage.mjs")

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def safe_relative(s):
    rel = PurePosixPath(s)
    if not rel.parts or rel.is_absolute() or ".." in rel.parts or "\\" in s:
        raise ValueError(f"Invalid source path {s!r}")
    return rel

def apply_edit(path, before, after):
    source = path.read_text(encoding="utf-8")
    if source.count(before) != 1:
        raise ValueError(f"Unexpected previous source in {path.name}")
    path.write_text(source.replace(before, after), encoding="utf-8")

def restore_and_edit(source, dest):
    with zipfile.ZipFile(source) as z:
        index = json.loads(z.read("source-index.json"))
        listing = index["files"]
        def write_blob(key, target):
            digest, mode = listing[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open("objects/" + digest) as inp, target.open("wb") as output:
                shutil.copyfileobj(inp, output, 1024 * 1024)
            if sha(target) != digest:
                raise ValueError(f"Corrupt source object {key}")
            target.chmod(0o755 if mode & 0o111 else 0o644)
        prefix = f"engines/{GAME}/"
        names = {key[len(prefix):] for key in listing if key.startswith(prefix)}
        if len(names) < 3500:
            raise ValueError("The supplied collection is missing the complete game engine")
        for rel in sorted(names):
            write_blob(prefix + rel, dest / safe_relative(rel))
        if (dest / "VERSION").read_text().strip() != OLD:
            raise ValueError("Unexpected release")
        for rel in WEB_UPDATES:
            webkey = f"games/{GAME}/" + rel
            if webkey not in listing:
                raise ValueError("The integrated site source is missing " + rel)
            write_blob(webkey, dest / "web" / safe_relative(rel))
        published = json.loads(z.read("objects/" + listing[f"games/{GAME}/public/game/engine.json"][0]))
        if (published["version"],published["sha256"]) != (OLD,OLD_ENGINE):
            raise ValueError("Wrong base engine")
    batch = sorted(dest.glob("sf_remodel*.go"))
    keys = set(re.findall(r'"([a-z][a-z0-9_]+)"', (dest / "sf_remodel.go").read_text().split("func sfRetainUnitDesign(",1)[1].split("func remodelFit",1)[0]))
    if keys != PROTECTED or len(batch) != 46:
        raise ValueError("Original individually rebuilt design set or batch layout changed")
    apply_edit(dest/"sf_mesh.go", "\treturn sfUnitGeometry(u, civ, pc, dir, anim, frame, true)\n}\n\nfunc sfUnitGeometry(u *UnitData, civ *CivData, pc RGB, dir float64, anim, frame int, visual bool) *Mesh {\n", "")
    apply_edit(dest/"sf_mesh.go", "\tif visual {\n\t\tsfRemodelUnit(m, c)\n\t}\n", "")
    apply_edit(dest/"sf_v17_visual.go", "\twwIFVChassis(m, c)\n", "")
    apply_edit(dest/"sf_sizes.go", "sfUnitGeometry(ud, civ, RGB{}, 0, 0, 0, false)", "sfUnitMesh(ud, civ, RGB{}, 0, 0, 0)")
    for p in batch:
        p.unlink()
    (dest/"VERSION").write_text(NEW+"\n")
    for rel in ("README.md", "web/public/game/index.html"):
        p=dest/rel
        p.write_text(p.read_text().replace(OLD,NEW))
    apply_edit(dest/"packaging/README.txt", "(Galactic Realms) "+OLD, "(Galactic Realms) "+NEW)
    apply_edit(dest/"packaging/README.txt", OLD+" 바뀐 점", NEW+" 바뀐 점\n- 71개 진영에서 일괄 개편했던 유닛 3,552종의 모형을 복원했습니다. 별도로 수정한 18종은 기존 개별 모형을 사용합니다.\n\n"+OLD+" 바뀐 점")
    mutable={"sf_mesh.go","sf_v17_visual.go","sf_sizes.go","VERSION","README.md","packaging/README.txt","web/public/game/index.html"}
    mutable.update("web/"+r for r in WEB_UPDATES)
    for rel in sorted(names - mutable - {p.name for p in batch}):
        assert sha(dest/rel) == listing[prefix+rel][0], rel
    print(f"Restored {len(batch)} batch-only source files to pre-batch absence; preserved individual designs and current map, economy, scale, and production sources.",flush=True)

def source_zip(game, output):
    files=sorted((p for p in game.rglob("*") if p.is_file()),key=lambda p:p.relative_to(game).as_posix())
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",allowZip64=True) as archive:
        for p in files:
            rel=p.relative_to(game).as_posix()
            ent=zipfile.ZipInfo(f"galactic-{NEW}-source/{rel}",(2000,1,1,0,0,0))
            ent.create_system=3
            ent.external_attr=(stat.S_IFREG | (0o755 if p.stat().st_mode & 0o111 else 0o644))<<16
            ent.compress_type=zipfile.ZIP_STORED if rel.endswith((".xz",".woff2",".png")) else zipfile.ZIP_DEFLATED
            with p.open("rb") as inp, archive.open(ent,"w") as out:
                shutil.copyfileobj(inp,out,1024*1024)
    print(output,output.stat().st_size,sha(output),flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection",type=Path,required=True)
    ap.add_argument("--previous-sha256",required=True)
    ap.add_argument("--game",type=Path,required=True)
    ap.add_argument("--source-zip",type=Path,required=True)
    args=ap.parse_args()
    if sha(args.collection)!=args.previous_sha256:
        raise SystemExit("Previous source ZIP checksum mismatch")
    if args.game.exists():
        raise SystemExit("The output source directory must be new")
    restore_and_edit(args.collection,args.game)
    source_zip(args.game,args.source_zip)

if __name__ == "__main__":
    main()
