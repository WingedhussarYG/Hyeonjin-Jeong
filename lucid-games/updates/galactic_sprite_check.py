"""Compare shipped sprites and the preserved pre-overhaul modeling path."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import zipfile

PREVIOUS_ZIP = "22a9be05a8d19d7dac497f673f976f8295f795ffe4f0c88e07b7001cbb6d7076"
HISTORICAL_ZIP = "4c9f95c1ea24292bccb7cd282e567f19d595aa33b368c1b023c77d69c436b573"
COLLECTION = "c7151e933cb8ce179a8b140bb0af3d4ecc01ed4fd73707babe4574639c97a548"
PROTECTED = """rae_executioner ter_thor ter_swannthor ter_blackhammer ter_odin ter_tychusodin
ter_xanthos nod_redeemer scr_annihilator scr_reaper scr_hexapod pro_colossus pro_warbringer
pro_wrathwalker pro_reaver pro_immortal pro_stalker pro_dragoon""".split()
ORDINARY = """gdi_mammoth atr_mongoose gc_bt_zakutank ban_gruntrider lotr_angmar_snow_troll
raa_ifv ter_marine bs_frigate_med wc_alliance_footman chs_raptor whf_beastmen_centigor
pro_hybrid_reaver""".split()
KEYS = PROTECTED + ORDINARY


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extract_program(archive, out):
    with zipfile.ZipFile(archive) as z:
        member, = [s for s in z.namelist() if Path(s).name == "galactic"]
        with z.open(member) as src, out.open("wb") as dest:
            shutil.copyfileobj(src, dest)
    out.chmod(0o755)


def render(exe, folder):
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, REALMS_NOSOUND="1", SHEET_ONLY=",".join(KEYS), SHEET_CELLS=str(folder),
               GOMAXPROCS="2", LIBGL_ALWAYS_SOFTWARE="1")
    proc = subprocess.run([exe, "-sheetkind", "sfcompare", "-sheet", folder / "units.png"],
                          env=env, cwd=folder, capture_output=True, text=True, timeout=180)
    (folder / "render.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-1500:])
    seen = [(int(i), key) for i, key in re.findall(r"^COMPARE (\d+) (\S+)", proc.stdout, re.M)]
    assert seen == list(enumerate(KEYS)), seen
    sprites = {}
    for i, key in seen:
        p = folder / f"cell_{i:03d}.png"
        dst = folder / (key + ".png")
        p.rename(dst)
        sprites[key] = digest(dst)
    print(f"Rendered {len(sprites)} actual sprites from {exe.name}", flush=True)
    return sprites


def get_previous(source_archive, baseline, old_native):
    assert digest(source_archive) == COLLECTION
    prefix = "engines/galactic-realms/"
    with zipfile.ZipFile(source_archive) as z:
        index = json.loads(z.read("source-index.json"))["files"]
        # Show how the already-downloaded desktop launcher resolves available modules.
        notes = []
        for name, (blob, _mode) in sorted(index.items()):
            lower = name.lower()
            if not ("desktop" in lower or lower.startswith("launcher/")):
                continue
            if name.startswith(("engines/", "games/", "modules/")) or any(x in lower for x in ("node_modules/", "vendor/", "offline/")):
                continue
            if Path(lower).suffix not in (".go", ".js", ".mjs", ".ts", ".cpp", ".rs", ".cs", ".py"):
                continue
            info = z.getinfo("objects/" + blob)
            if info.file_size > 950_000:
                continue
            lines = z.read(info).decode(errors="replace").splitlines()
            if not any("catalog" in line.lower() for line in lines):
                continue
            matches = [i for i, line in enumerate(lines) if re.search(
                r"catalog.{0,100}(http|embedded|bundled|online|content|local|fetch|cache)|"
                r"(http|embedded|bundled|online|local|content|fetch|cache).{0,100}catalog|"
                r"(installed|module).{0,50}version|version.{0,40}(installed|module)", line, re.I)]
            for i in matches[:8]:
                notes.append(f"{name}:{i + 1} {lines[i].strip()[:360]}")
            if len(notes) >= 45:
                break
        (baseline.parent / "desktop-catalog-lines.txt").write_text("\n".join(notes))
        print("Desktop launcher module selection:\n" + "\n".join(notes), flush=True)
        for name, (blob, mode) in index.items():
            if not name.startswith(prefix):
                continue
            target = baseline / name[len(prefix):]
            assert target.is_relative_to(baseline) and ".." not in target.parts
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open("objects/" + blob) as inp, target.open("wb") as out:
                shutil.copyfileobj(inp, out)
            assert digest(target) == blob
            target.chmod(0o755 if mode & 0o111 else 0o644)
        public = "games/galactic-realms/public"
        manifest = json.loads(z.read("objects/" + index[public + "/releases/manifest.json"][0]))
        row, = [p for p in manifest["packages"] if p["os"] == "linux"]
        assert row["sha256"] == PREVIOUS_ZIP and manifest["version"] == "2.5.1"
        if all(public + "/" + p.lstrip("/") in index for p in row["parts"]):
            with old_native.open("wb") as out:
                for part in row["parts"]:
                    with z.open("objects/" + index[public + "/" + part.lstrip("/")][0]) as inp:
                        shutil.copyfileobj(inp, out)
    if not old_native.exists():
        url = "https://galactic-realms.maxfaine.chatgpt.site/downloads/" + row["filename"]
        subprocess.run(["curl", "-fsSL", "--retry", "2", "--max-time", "180", url,
                        "-o", old_native], check=True)
    assert digest(old_native) == PREVIOUS_ZIP


def check_sources(baseline, source_archive):
    prefix = "galactic-2.5.2-source/"
    with zipfile.ZipFile(source_archive) as z:
        original = {p.name: p for p in baseline.glob("*.go")}
        current = {n[len(prefix):] for n in z.namelist()
                   if n.startswith(prefix) and "/" not in n[len(prefix):] and n.endswith(".go")}
        removed = {n for n in original if n.startswith("sf_remodel")}
        assert len(removed) == 46 and set(original) - removed == current
        for name in current:
            before = original[name].read_bytes()
            after = z.read(prefix + name)
            if name == "sf_mesh.go":
                before = before.replace(
                    b"\treturn sfUnitGeometry(u, civ, pc, dir, anim, frame, true)\n}\n\n"
                    b"func sfUnitGeometry(u *UnitData, civ *CivData, pc RGB, dir float64, "
                    b"anim, frame int, visual bool) *Mesh {\n", b"")
                before = before.replace(b"\tif visual {\n\t\tsfRemodelUnit(m, c)\n\t}\n", b"")
            elif name == "sf_v17_visual.go":
                before = before.replace(b"\twwIFVChassis(m, c)\n", b"")
            elif name == "sf_sizes.go":
                before = before.replace(b"sfUnitGeometry(ud, civ, RGB{}, 0, 0, 0, false)",
                                        b"sfUnitMesh(ud, civ, RGB{}, 0, 0, 0)")
            assert before == after, name
        alt = z.read(prefix + "sf_v17_visual.go").decode()
    begin = alt.index("func v17IFVMesh(")
    end = alt.index("\nfunc ", begin + 6)
    return alt[begin:end].replace("func v17IFVMesh(", "func archivedIFV(")


GO_CHECK = r'''package main
import ("encoding/csv"; "fmt"; "image"; "image/png"; "os"; "path/filepath"; "reflect";
"sort"; "strings"; "testing"; "github.com/hajimehoshi/ebiten/v2")

type archiveSampler struct { units map[string]*SFUnit; keys []string; dir string; frames int; finished bool }
func (s *archiveSampler) Layout(w,h int)(int,int){return 64,64}
func (s *archiveSampler) Update() error {if s.finished {return ebiten.Termination};return nil}
func (s *archiveSampler) Draw(dst *ebiten.Image){
    s.frames++
    if s.frames<2||s.finished{return}
    for _,k:=range s.keys{
        u:=s.units[k]; m:=sfUnitGeometry(u.U,u.f.civ,sheetPC(),.6,0,0,false)
        sprite:=RenderMesh(m,1.6,true,.3)
        img:=image.NewRGBA(image.Rect(0,0,sprite.W,sprite.H));sprite.Img.ReadPixels(img.Pix)
        f,err:=os.Create(filepath.Join(s.dir,k+".png"));if err!=nil{panic(err)}
        if err:=png.Encode(f,img);err!=nil{panic(err)};if err:=f.Close();err!=nil{panic(err)}
    }
    s.finished=true
}
func TestArchivedUnitDesigns(t *testing.T){
    loadGameData()
    var units []*SFUnit
    for _,u:=range sfUnitByID {if u.U!=nil&&u.f!=nil&&u.f!=sfCheatFac{units=append(units,u)}}
    sort.Slice(units,func(i,j int)bool{return units[i].Key<units[j].Key})
    dir:=os.Getenv("ARCHIVE_ART_OUT")
    f,err:=os.Create(filepath.Join(dir,"unit-designs.csv"));if err!=nil{t.Fatal(err)}
    defer f.Close();w:=csv.NewWriter(f);w.Write([]string{"처리","작품 ID","진영 ID","유닛 이름","유닛 ID"})
    byKey:=map[string]*SFUnit{};factions:=map[string]bool{};kept,changed:=0,0
    for _,u:=range units{
        base:=sfUnitGeometry(u.U,u.f.civ,sheetPC(),.6,0,0,false)
        bulk:=sfUnitMesh(u.U,u.f.civ,sheetPC(),.6,0,0)
        same:=reflect.DeepEqual(base,bulk)
        if same!=sfRetainUnitDesign(u.Key){t.Fatalf("unmatched archived mesh %s",u.Key)}
        disposition:="이전 디자인 복원";if same{kept++;disposition="개별 디자인 유지"}else{changed++}
        byKey[u.Key]=u;factions[u.f.Key]=true
        w.Write([]string{disposition,u.f.Franchise,u.f.Key,u.Name,u.Key})
    }
    w.Flush();if err:=w.Error();err!=nil{t.Fatal(err)}
    if len(units)!=3570||len(factions)!=71||kept!=18||changed!=3552{t.Fatal(len(units),len(factions),kept,changed)}
    ifv:=byKey["raa_ifv"]; poses:=make([]*Mesh,0,7)
    for mode:=int8(1);mode<=7;mode++{
        a:=archivedIFV(ifv.U,ifv.f.civ,sheetPC(),.6,0,0,mode)
        b:=v17IFVMesh(ifv.U,ifv.f.civ,sheetPC(),.6,0,0,mode)
        if reflect.DeepEqual(a,b){t.Fatalf("IFV %d retained bulk chassis",mode)}
        for _,p:=range poses{if reflect.DeepEqual(a,p){t.Fatalf("IFV %d duplicated turret",mode)}}
        poses=append(poses,a)
    }
    fmt.Printf("Verified %d factions, %d unit definitions, %d rollbacks, %d retained, 7 IFV equipment modes\n",len(factions),len(units),changed,kept)
    s:=&archiveSampler{units:byKey,keys:strings.Split(os.Getenv("ARCHIVE_ART_KEYS"),","),dir:dir}
    ebiten.SetWindowSize(64,64);if err:=ebiten.RunGame(s);err!=nil{t.Fatal(err)};if !s.finished{t.Fatal("no rendered reference")}
}
'''


def source_reference(baseline, alternate_ifv, out):
    out.mkdir()
    (baseline / "zz_archived_designs_test.go").write_text(GO_CHECK + "\n" + alternate_ifv)
    pathlib_lib = baseline / "packaging" / "rebuild.py"
    driver = runpy.run_path(str(pathlib_lib))
    env = dict(os.environ, GOMAXPROCS="2", GOWORK="off", GOPROXY="off", GOSUMDB="off",
               GOTOOLCHAIN="local", GOOS="linux", GOARCH="amd64", GOFLAGS="-p=1 -mod=vendor",
               ARCHIVE_ART_OUT=str(out), ARCHIVE_ART_KEYS=",".join(KEYS),
               REALMS_NOSOUND="1", LIBGL_ALWAYS_SOFTWARE="1",
               GOCACHE=str(baseline / ".build" / "audit-gocache"))
    native = driver["native_environment"](env)
    go = Path(native["GOROOT"]) / "bin" / "go"
    test = [go, "test", "-buildvcs=false", "-trimpath", "-toolexec=galactic-go-tool",
            "-gcflags=realms=-dwarf=false -c=1 -l", "-run", "^TestArchivedUnitDesigns$",
            "-timeout=10m", "-v", "."]
    subprocess.run(test, env=native, cwd=baseline, check=True, timeout=800)
    return {k: digest(out / (k + ".png")) for k in KEYS}


def main():
    p = argparse.ArgumentParser()
    for name in ("collection", "release", "working", "out"):
        p.add_argument("--" + name, required=True, type=Path)
    a=p.parse_args()
    work, out = a.working.resolve(), a.out.resolve()
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    sums = {name: sha for sha, name in
            [line.split() for line in (a.release / "galactic-2.5.2-checksums.txt").read_text().splitlines()]}
    new_zip, new_source = [a.release / ("galactic-2.5.2-" + suffix) for suffix in ("linux-x64.zip","source.zip")]
    assert all(digest(p)==sums[p.name] for p in (new_zip,new_source))
    baseline, old_zip = work/"source-251", work/"previous-linux.zip"
    get_previous(a.collection, baseline, old_zip)
    shutil.copyfile(work / "desktop-catalog-lines.txt", out / "desktop-catalog-lines.txt")
    alternate = check_sources(baseline, new_source)
    results = {}
    for label, archive in (("2.5.1",old_zip),("2.5.2",new_zip)):
        exe = work/("galactic-"+label);extract_program(archive,exe)
        results[label] = render(exe,out/label)
    old,new=results["2.5.1"],results["2.5.2"]
    assert all(old[k]==new[k] for k in PROTECTED), [k for k in PROTECTED if old[k]!=new[k]]
    assert all(old[k]!=new[k] for k in ORDINARY), [k for k in ORDINARY if old[k]==new[k]]
    print("Shipped Linux packages: all 18 individual sprites identical; all 12 batch examples changed.",flush=True)
    historical=work/"2.4.5-linux.zip"
    site="https://galactic-realms.maxfaine.chatgpt.site/downloads/galactic-2.4.5-linux-x64.zip"
    got=subprocess.run(["curl","-fsSL","--connect-timeout","8","--max-time","35","-o",historical,site])
    if got.returncode==0 and digest(historical)==HISTORICAL_ZIP:
        exe=work/"galactic-2.4.5";extract_program(historical,exe)
        results["2.4.5"]=render(exe,out/"2.4.5")
        assert results["2.4.5"]==new
    ref=source_reference(baseline,alternate,out/"archived-pre-overhaul")
    assert ref==new, [k for k in KEYS if new[k]!=ref[k]]
    results["archived-pre-overhaul"]=ref
    (out/"sprite-sha256.json").write_text(json.dumps(results,indent=2))
    print("All 30 shipped 2.5.2 sprites reproduce the preserved pre-overhaul renderer byte for byte.",flush=True)

if __name__=="__main__":
    main()
