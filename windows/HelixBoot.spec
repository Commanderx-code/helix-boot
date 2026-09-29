# PyInstaller build for the Windows app:  pyinstaller windows/HelixBoot.spec
# (from the repo root). One file, no console, asks for admin (Ventoy writes to disks).
import sys
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

a = Analysis([str(root / "windows" / "helix_boot.py")], datas=datas)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="HelixBoot",
    console=False,
    uac_admin=sys.platform == "win32",
    upx=False,
)
