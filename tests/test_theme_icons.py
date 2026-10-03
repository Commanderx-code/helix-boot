"""The boot-menu icons: built from their masters, one for every menu class."""
import importlib.util
from pathlib import Path
import shutil
import struct
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
HAVE_PILLOW = importlib.util.find_spec("PIL") is not None


class ToolIcons(unittest.TestCase):
    @unittest.skipUnless(HAVE_PILLOW, "theme rebuild verification needs Pillow")
    def test_default_set_is_built_from_its_masters(self):
        spec = importlib.util.spec_from_file_location("theme_build", ROOT / "theme/build-theme.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        masters = sorted(build.ICON_DIR.glob("*.png"))
        self.assertGreater(len(masters), 40)
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            build.HERE = repo / "theme"
            build.HERE.mkdir()
            shutil.copy2(ROOT / "tools.toml", repo / "tools.toml")
            build.icons()
            built = {f.name: f.read_bytes() for f in (build.HERE / "icons").iterdir()}
        committed = {f.name: f.read_bytes() for f in (ROOT / "theme/icons").iterdir()}
        self.assertEqual(sorted(built), sorted(committed))
        self.assertEqual(built, committed, "run theme/build-theme.py: theme/icons is out of date")
        tools = tomllib.loads((ROOT / "tools.toml").read_text())
        for t in tools["tool"]:                             # every shipped boot tool is in the set
            if t["kind"] == "iso":
                self.assertTrue((build.ICON_DIR / f"{t['name']}.png").is_file(), f"no master for {t['name']}")
        for m in masters:                                   # small masters, one per menu class
            self.assertIn(m.name, committed)
            w, h = struct.unpack(">II", m.read_bytes()[16:24])
            self.assertTrue(0 < w <= 256 and 0 < h <= 256, m.name)
        for name, data in committed.items():                # what the boot loader shows: 40x40, always
            self.assertEqual(struct.unpack(">II", data[16:24]), (40, 40), name)
        tools = tomllib.loads((ROOT / "tools.toml").read_text())
        for cls in ([t["name"] for t in tools["tool"] if t["kind"] == "iso"]
                    + [f"cat-{c['id']}" for c in tools["category"]]
                    + ["vtoydir", "vtoyret", "vtoyiso", "vtoyimg", "vtoywim", "vtoyefi", "vtoyvhd", "vtoyvtoy"]):
            self.assertIn(f"{cls}.png", committed, "no icon for it")

    @unittest.skipUnless(HAVE_PILLOW, "theme rebuild verification needs Pillow")
    def test_a_tool_without_a_master_gets_a_letter_badge(self):
        spec = importlib.util.spec_from_file_location("theme_build", ROOT / "theme/build-theme.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            build.HERE = repo / "theme"
            build.HERE.mkdir()
            (repo / "tools.toml").write_text('[[tool]]\nname = "brand-new"\ntitle = "Brand New"\nkind = "iso"\n')
            build.fallback_icons(repo / "out")
            data = (repo / "out/brand-new.png").read_bytes()
            self.assertEqual(struct.unpack(">II", data[16:24]), (40, 40))
            self.assertTrue((repo / "out/vtoydir.png").is_file())

    def test_only_the_packs_that_are_built_are_shipped(self):
        packs = sorted(d.name for d in (ROOT / "theme/icon-packs").iterdir() if (d / "pack.toml").is_file())
        self.assertEqual(packs, ["badges"])
