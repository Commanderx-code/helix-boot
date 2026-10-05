# PyInstaller build for the Mac program:  pyinstaller mac/HelixBoot-mac.spec
# (from the repo root, on a Mac). One file, run from Terminal: helix-mac with Python and the
# engine's files inside, so nothing else has to be installed.
from pathlib import Path

root = Path(SPECPATH).parent
datas = [
    (str(root / "helix"), "."),
    (str(root / "tools.toml"), "."),
    (str(root / "pe" / "launcher"), "pe/launcher"),
    (str(root / "pe" / "lazarus"), "pe/lazarus"),
    (str(root / "byo" / "README.md"), "byo"),
]
datas += [(str(p), (Path("theme") / p.parent.relative_to(root / "theme")).as_posix())
          for p in (root / "theme").rglob("*")
          if p.is_file() and p.suffix not in (".py", ".pyc") and "__pycache__" not in p.parts]

a = Analysis([str(root / "mac" / "helix-mac")], datas=datas)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="HelixBoot-mac",
    console=True,
    upx=False,
)
