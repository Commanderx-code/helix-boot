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
            build.icons()
            for name in registry:
                generated = build.HERE / "icons" / f"{name}.png"
                self.assertEqual(generated.read_bytes(), (ROOT / "theme/icons" / generated.name).read_bytes(), name)
            self.assertTrue((build.HERE / "icons/cat-live.png").exists())

    @unittest.skipUnless(HAVE_PILLOW, "theme asset validation needs Pillow")
    def test_missing_registered_artwork_is_not_silently_badged(self):
        spec = importlib.util.spec_from_file_location("theme_build", ROOT / "theme/build-theme.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as temp:
            build.TOOL_ICON_DIR = Path(temp)
            with self.assertRaises(FileNotFoundError):
                build.tool_icon({"name": "rescuezilla"}, {"rescuezilla": {"file": "missing.png"}}, Path(temp))


if __name__ == "__main__":
    unittest.main()
