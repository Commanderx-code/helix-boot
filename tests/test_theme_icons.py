"""Keep curated tool artwork intact across theme rebuilds."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "docs/artwork/tool-icons"
HAVE_PILLOW = importlib.util.find_spec("PIL") is not None


class ToolIcons(unittest.TestCase):
    def test_source_inventory_and_integrity(self):
        registry = json.loads((SOURCES / "sources.json").read_text())
        tools = tomllib.loads((ROOT / "tools.toml").read_text())["tool"]
        self.assertEqual(set(registry), {t["name"] for t in tools if t["kind"] == "iso"})
        for name, entry in registry.items():
            if entry["kind"] == "fallback":
                self.assertNotIn("file", entry)
                self.assertTrue(entry["note"])
                continue
            self.assertEqual(entry["file"], name + ".png")
            data = (SOURCES / entry["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            w, h = struct.unpack(">II", data[16:24])
            self.assertTrue(0 < w <= 256 and 0 < h <= 256)
            self.assertTrue(entry["source"])

    @unittest.skipUnless(HAVE_PILLOW, "theme rebuild verification needs Pillow")
    def test_rebuild_preserves_curated_icons_and_fallbacks(self):
        spec = importlib.util.spec_from_file_location("theme_build", ROOT / "theme/build-theme.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        registry = json.loads((SOURCES / "sources.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            build.HERE = repo / "theme"
            build.HERE.mkdir()
            shutil.copy2(ROOT / "tools.toml", repo / "tools.toml")
            build.classic_icons(repo / "classic")                       # the classic set: the tools' own logos
            for name in registry:
                generated = repo / "classic" / f"{name}.png"
                self.assertEqual(generated.read_bytes(),
                                 (ROOT / "theme/icon-packs/classic" / generated.name).read_bytes(), name)
            self.assertTrue((repo / "classic/cat-live.png").exists())

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

    @unittest.skipUnless(HAVE_PILLOW, "theme asset validation needs Pillow")
    def test_missing_registered_artwork_is_not_silently_badged(self):
        spec = importlib.util.spec_from_file_location("theme_build", ROOT / "theme/build-theme.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as temp:
            build.TOOL_ICON_DIR = Path(temp)
            with self.assertRaises(FileNotFoundError):
                build.tool_icon({"name": "rescuezilla"}, {"rescuezilla": {"file": "missing.png"}}, Path(temp))


class Presets(unittest.TestCase):
    def test_every_preset_is_complete(self):
        presets = sorted(p for p in (ROOT / "theme/presets").iterdir() if p.is_dir())
        self.assertGreaterEqual(len(presets), 6)
        for p in presets:
            with self.subTest(preset=p.name):
                meta = tomllib.loads((p / "preset.toml").read_text(encoding="utf-8"))
                self.assertTrue(meta["title"] and meta["description"])
                text = (p / "theme.txt").read_text(encoding="utf-8")
                self.assertIn("@VTOY_HOTKEY_TIP@", text)                # Ventoy's hotkeys stay on screen
                for key in ("icon_width", "icon_height", "item_icon_space"):   # "icons off" sets these to 0
                    self.assertRegex(text, rf"(?m)^\s*{key}\s*=\s*\d+")
                for name in ("background.png", "splash.png"):
                    self.assertEqual((p / name).read_bytes()[:8], b"\x89PNG\r\n\x1a\n", name)
                for font in set(__import__("re").findall(r'font\s*[:=]\s*"([^"]+)"', text)):
                    have = [f.read_bytes() for f in list(p.glob("*.pf2")) +
                            ([] if meta.get("standalone") else list((ROOT / "theme/fonts").glob("*.pf2")))]
                    self.assertTrue(font.startswith("Unifont") or any(font.encode() in f for f in have),
                                    f"{font}: no .pf2 for it")          # Unifont is Ventoy's own
                if meta.get("standalone"):                              # someone else's theme: credit and licence
                    self.assertTrue((p / "NOTICE.md").is_file())
                    self.assertTrue((p / "LICENSE").is_file() or (p / "COPYING").is_file())


if __name__ == "__main__":
    unittest.main()
