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

# What Windows shows under Properties > Details, and what a code-signing service checks:
# the product's name and the version of `helix` this was built from.
import re
VERSION = re.search(r'^__version__ = "([\d.]+)"', (root / "helix").read_text(encoding="utf-8"), re.M).group(1)
numbers = tuple(int(n) for n in (VERSION.split(".") + ["0"] * 4)[:4])
version_file = None
if sys.platform == "win32":
    version_file = Path(SPECPATH) / "version-info.txt"       # (git-ignored; rewritten on every build)
    strings = {
        "CompanyName": "Helix Boot",
        "FileDescription": "Helix Boot",
        "FileVersion": VERSION,
        "InternalName": "HelixBoot",
        "LegalCopyright": "MIT License. https://github.com/Commanderx-code/helix-boot",
        "OriginalFilename": "HelixBoot.exe",
        "ProductName": "Helix Boot",
        "ProductVersion": VERSION,
    }
    version_file.write_text(
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0, OS=0x40004,\n"
        "                    fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[\n"
        "    StringFileInfo([StringTable('040904B0', [\n"
        + "".join(f"      StringStruct({k!r}, {v!r}),\n" for k, v in strings.items())
        + "    ])]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])]),\n"
        "  ],\n"
        ")\n", encoding="utf-8")

a = Analysis([str(root / "windows" / "helix_boot.py")], datas=datas)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="HelixBoot",
    console=False,
    uac_admin=sys.platform == "win32",
    upx=False,
    version=str(version_file) if version_file else None,
)
