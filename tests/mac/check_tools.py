#!/usr/bin/env python3
"""Check the tools for a Mac on a real Mac: each download opens as macOS would open it, and what
is inside is whole, signed by its developer and let through by Gatekeeper.

    helix fetch $(tests/mac/check_tools.py --names)     # the Mac tools only
    tests/mac/check_tools.py                            # check what was fetched

A download that can't be opened, holds no app, or whose signature is broken fails the run. One that
is merely unsigned or not notarized is reported: macOS then asks before opening it, which the
stick's Mac/README.txt explains. Needs macOS (hdiutil, codesign, spctl, pkgutil); CI runs it on
GitHub's Mac runners.
"""
import argparse
import importlib.machinery
import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_helix():
    loader = importlib.machinery.SourceFileLoader("helix", str(ROOT / "helix"))
    spec = importlib.util.spec_from_loader("helix", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(*cmd, stdin: str | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], input=stdin, capture_output=True, text=True, timeout=timeout)


def found(folder: Path, suffix: str, depth: int = 3) -> list[Path]:
    """Bundles or files with this suffix, not looking inside an app for more."""
    hits = []

    def walk(d: Path, left: int) -> None:
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for p in entries:
            if p.name.startswith("."):
                continue
            if p.suffix.lower() == suffix:
                hits.append(p)
            elif p.is_dir() and not p.is_symlink() and p.suffix.lower() != ".app" and left:
                walk(p, left - 1)

    walk(folder, depth)
    return hits


def check_app(app: Path) -> tuple[list[str], list[str], list[str]]:
    """(what it is, warnings, failures) for one .app."""
    facts, warns, fails = [], [], []
    try:
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        return facts, warns, [f"{app.name}: no readable Info.plist, so it isn't an app macOS can open"]
    facts.append(f"{app.name} {info.get('CFBundleShortVersionString') or info.get('CFBundleVersion') or '?'}")
    binary = app / "Contents/MacOS" / str(info.get("CFBundleExecutable", ""))
    if not binary.is_file():
        fails.append(f"{app.name}: its program ({binary.name or '?'}) is missing")
    else:
        archs = run("lipo", "-archs", binary).stdout.strip()
        facts.append(archs or "unknown architecture")
    if info.get("LSMinimumSystemVersion"):
        facts.append(f"macOS {info['LSMinimumSystemVersion']}+")

    sign = run("codesign", "--verify", "--deep", "--strict", app)
    if sign.returncode == 0:
        detail = run("codesign", "-dvv", app).stderr
        who = next((line.split("=", 1)[1] for line in detail.splitlines() if line.startswith("Authority=")), "ad hoc")
        facts.append(f"signed: {who}")
    elif "not signed at all" in sign.stderr:
        warns.append(f"{app.name} isn't signed: macOS asks before opening it")
    else:
        fails.append(f"{app.name}: its signature doesn't verify ({sign.stderr.strip().splitlines()[-1][:160]})")
    gate = run("spctl", "--assess", "--type", "execute", "-vv", app)
    said = (gate.stderr or gate.stdout).strip().replace("\n", "; ")
    if gate.returncode == 0:
        facts.append("Gatekeeper: " + ("notarized" if "Notarized" in said else "accepted"))
    elif sign.returncode == 0:
        warns.append(f"{app.name} is signed but Gatekeeper doesn't accept it ({said[-120:]}): macOS asks before opening it")
    return facts, warns, fails


def check_pkg(pkg: Path) -> tuple[list[str], list[str], list[str]]:
    facts, warns, fails = [pkg.name], [], []
    sign = run("pkgutil", "--check-signature", pkg)
    lines = [line.strip() for line in sign.stdout.splitlines()]
    if sign.returncode == 0:
        who = next((line.split(".", 1)[1].strip() for line in lines if line.startswith("1.")), "a developer")
        facts.append(f"signed: {who}")
        facts.append("notarized" if any("trusted by the Apple notary" in line for line in lines) else "not notarized")
        if "not notarized" in facts:
            warns.append(f"{pkg.name} is signed but not notarized: macOS asks before opening it")
    elif any("no signature" in line.lower() for line in lines):
        warns.append(f"{pkg.name} isn't signed: macOS asks before opening it")
    else:
        fails.append(f"{pkg.name}: its signature doesn't verify ({(sign.stdout or sign.stderr).strip()[-160:]})")
    return facts, warns, fails


def check_download(path: Path, work: Path) -> tuple[list[str], list[str], list[str]]:
    """Open one download as macOS would, and check the apps and installers in it."""
    name, mounted = path.name.lower(), None
    try:
        if name.endswith(".dmg"):
            mounted = work / "volume"
            mounted.mkdir()
            att = run("hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mounted, path,
                      stdin="Y\n" * 4)                                  # (a licence to agree to, on some)
            if att.returncode:
                return [], [], [f"the disk image doesn't open ({att.stderr.strip()[-160:]})"]
            inside = mounted
        elif name.endswith(".zip"):
            inside = work / "unzipped"
            got = run("ditto", "-x", "-k", path, inside)
            if got.returncode:
                return [], [], [f"the zip doesn't unpack ({got.stderr.strip()[-160:]})"]
        elif name.endswith((".tar.bz2", ".tar.gz", ".tgz")):
            inside = work / "untarred"
            inside.mkdir()
            got = run("tar", "-xf", path, "-C", inside)
            if got.returncode:
                return [], [], [f"the archive doesn't unpack ({got.stderr.strip()[-160:]})"]
        elif name.endswith(".pkg"):
            return check_pkg(path)
        else:
            return [], [f"{path.name}: not a kind of file this knows how to open"], []

        facts, warns, fails = [], [], []
        apps, pkgs = found(inside, ".app"), found(inside, ".pkg")
        for item, check in [(a, check_app) for a in apps] + [(p, check_pkg) for p in pkgs]:
            f, w, x = check(item)
            facts.append(", ".join(f))
            warns += w
            fails += x
        if not apps and not pkgs:                                       # command-line tools, e.g. TestDisk
            programs = [p for p in sorted(inside.rglob("*")) if p.is_file() and not p.is_symlink()
                        and os.access(p, os.X_OK) and "Mach-O" in run("file", "-b", p).stdout]
            if not programs:
                fails.append("nothing a Mac can run is inside")
            else:
                archs = sorted({a for p in programs for a in run("lipo", "-archs", p).stdout.split()})
                facts.append(f"{len(programs)} program(s) ({', '.join(p.name for p in programs[:4])}"
                             f"{', …' if len(programs) > 4 else ''}), {' '.join(archs) or 'unknown architecture'}")
        return facts, warns, fails
    finally:
        if mounted and mounted.exists():
            run("hdiutil", "detach", "-force", mounted)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--names", action="store_true", help="print the names of the tools for a Mac, for `helix fetch`")
    args = ap.parse_args()
    cr = load_helix()
    cfg = cr.Config(repo=ROOT)
    tools = [t for t in cfg.enabled(kinds={"app"}) if t.get("platform") == "mac"]
    if args.names:
        print(" ".join(t["name"] for t in tools))
        return 0
    if sys.platform != "darwin":
        sys.exit("this checks the Mac tools on a Mac: run it on macOS")
    lock = cr.load_lock(cfg)
    oks, warns, fails = [], [], []
    for t in tools:
        entry = lock.get(t["name"])
        path = cfg.cache / t["name"] / entry["final"] if entry else None
        if not path or not path.is_file():
            fails.append(f"{t['title']}: not fetched")
            print(f"✗ {fails[-1]}")
            continue
        work = Path(tempfile.mkdtemp(prefix="helix-mac-"))
        try:
            facts, w, x = check_download(path, work)
        except subprocess.TimeoutExpired as e:
            facts, w, x = [], [], [f"timed out ({e.cmd[0]})"]
        finally:
            shutil.rmtree(work, ignore_errors=True)
        line = f"{t['title']} ({path.name}): " + "; ".join(facts or ["—"])
        for msg in x:
            fails.append(f"{t['title']}: {msg}")
            print(f"✗ {fails[-1]}")
        for msg in w:
            warns.append(f"{t['title']}: {msg}")
            print(f"! {warns[-1]}")
        if not x:
            oks.append(line)
            print(f"✓ {line}")
    if os.environ.get("GITHUB_ACTIONS"):          # one annotation per level (GitHub shows at most 10 of each)
        for level, title, lines in (("notice", "opens on a Mac", oks), ("warning", "macOS will ask first", warns),
                                    ("error", "failed", fails)):
            if lines:
                print(f"::{level} title={title}::" + "%0A".join(s.replace("%", "%25") for s in lines))
    print(f"\n{len(oks)} of {len(tools)} tools for a Mac open on macOS {run('sw_vers', '-productVersion').stdout.strip()}"
          f" ({run('uname', '-m').stdout.strip()}); {len(warns)} warning(s), {len(fails)} failure(s).")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
