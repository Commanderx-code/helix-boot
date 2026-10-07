# PyInstaller build for the Linux window:  pyinstaller linux/HelixBoot-linux.spec
# (from the repo root). One file with Python, Tk and the engine's files inside, so nothing has
# to be installed. Not root: it asks for your password only where a step needs it.
from pathlib import Path

root = Path(SPECPATH).parent
datas = [
    (str(root / "helix"), "."),
    (str(root / "tools.toml"), "."),
    (str(root / "pe" / "launcher"), "pe/launcher"),
    (str(root / "pe" / "lazarus"), "pe/lazarus"),
    (str(root / "byo" / "README.md"), "byo"),
    (str(root / "windows" / "logo.png"), "."),          # the mark in the windows' header
    (str(root / "windows" / "icon.png"), "."),          # the windows' own icon
    (str(root / "scripts" / "common.sh"), "scripts"),   # which disks hold the running system
]
datas += [(str(p), (Path("theme") / p.parent.relative_to(root / "theme")).as_posix())
          for p in (root / "theme").rglob("*")
          if p.is_file() and p.suffix not in (".py", ".pyc") and "__pycache__" not in p.parts]

# The window itself is windows/helix_boot.py, imported as a module: found here, and read for
# what it imports (it names everything the engine needs, which is loaded from a file).
a = Analysis([str(root / "linux" / "helix_gui.py")], pathex=[str(root / "windows")], datas=datas)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="HelixBoot-linux",
    console=True,           # started from a terminal it says why it can't start; from a file manager nothing shows
    upx=False,
)
