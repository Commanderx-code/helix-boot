"""Regression cases for imported theme paths, system folders and cached app integrity."""
import importlib.util
import json
import os
import subprocess
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_helix as fixtures


cr = fixtures.cr


class TestFollowupSafety(fixtures.Base):
    def test_resolved_system_folder_alias_is_reserved(self):
        alias = self.stick / "SYSTEM~1"
        canonical = self.stick / "System Volume Information"
        real_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return canonical if path == alias else real_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve), self.assertRaises(cr.RescueError):
            cr._inside(self.stick, "SYSTEM~1", "apps folder")

    def test_pack_cannot_write_under_exempt_system_folders(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        sentinel = outside / "victim"
        sentinel.write_bytes(b"before")
        for folder in sorted(cr.SYSTEM_DIRS):
            with self.subTest(folder=folder):
                root = self.stick / folder
                root.mkdir()
                (root / ".app.new").symlink_to(outside, target_is_directory=True)
                pack = self.tmp / "attack.zip"
                with zipfile.ZipFile(pack, "w") as z:
                    z.writestr(cr.PACK_META, json.dumps(dict(format=cr.PACK_FORMAT, iso_root="ISO",
                        apps_root=folder, isos=[], apps={"app": "1"})))
                    z.writestr(f"stick/{folder}/app/victim", b"after")
                    z.writestr("stick/ventoy/ventoy.json", "{}")
                with self.assertRaisesRegex(cr.RescueError, "unsafe"):
                    self.run_quiet(cr.cmd_unpack, self.cfg, SimpleNamespace(pack=str(pack),
                        target=str(self.stick), init=True, dry_run=False, verify=False, no_prune=False))
                self.assertEqual(sentinel.read_bytes(), b"before")
                for alias in (folder.upper(), folder + ".", folder + " "):
                    with self.assertRaises(cr.RescueError):
                        cr._safe_rel("stick/" + alias + "/file")

    def theme(self):
        from PIL import Image
        src = self.stick / cr.THEME_SRC
        src.mkdir(parents=True)
        (self.stick / cr.BASE_JSON).write_text('{"theme": {}}')
        Image.new("RGB", (20, 20), "blue").save(src / "background.png")
        (src / "theme.txt").write_text('desktop-image: "background.png"\n')
        return src

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "theme fixtures need Pillow")
    def test_background_rejects_drive_paths_and_keeps_normal_filename(self):
        src = self.theme()
        self.assertEqual(cr._desktop_image(src), "background.png")
        for name in ("C:victim", "C:/victim", "//server/share/pic.png", "../victim", ".", ".. "):
            with self.subTest(name=name):
                (src / "theme.txt").write_text(f'desktop-image: "{name}"\n')
                with self.assertRaises(cr.RescueError):
                    cr._desktop_image(src)
        (src / "theme.txt").write_text('desktop-image: "C:victim"\n')
        custom = self.stick / cr.LOOK_DIR
        custom.mkdir()
        (custom / "background.png").write_bytes(b"attacker bytes")
        with self.assertRaises(cr.RescueError):
            cr._build_look(self.cfg, self.stick, dict(cr.LOOK_DEFAULT, background="custom"),
                           self.tmp / "built", frames=False)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "theme previews need Pillow")
    def test_preview_confines_image_and_pixmap_access_before_stat(self):
        src = self.theme()
        out = self.tmp / "preview.png"
        (src / "assets").mkdir()
        (src / "assets/pic.png").write_bytes((src / "background.png").read_bytes())
        (src / "theme.txt").write_text('desktop-image: "background.png"\n+ image { file = "assets/pic.png" }')
        cr.look_preview(self.cfg, self.stick, cr.LOOK_DEFAULT, out)
        self.assertTrue(out.is_file())
        for resource in (str(self.tmp / "outside.png"), "../outside.png", "C:outside.png",
                         "//attacker.invalid/share/pic.png", r"\\attacker.invalid\share\pic.png"):
            for block in (f'+ image {{ file = "{resource}" }}',
                          f'+ boot_menu {{ menu_pixmap_style = "{resource}*.png" }}'):
                with self.subTest(resource=resource, block=block):
                    (src / "theme.txt").write_text('desktop-image: "background.png"\n' + block)
                    real_stat = Path.stat

                    def guarded_stat(path, *args, **kwargs):
                        self.assertNotIn("outside", str(path))
                        self.assertNotIn("attacker.invalid", str(path))
                        return real_stat(path, *args, **kwargs)

                    with patch.object(Path, "stat", guarded_stat), self.assertRaises(cr.RescueError):
                        cr.look_preview(self.cfg, self.stick, cr.LOOK_DEFAULT, out)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "theme previews need Pillow")
    def test_preview_rejects_source_links_before_copying(self):
        src = self.theme()
        outside = self.tmp / "outside.png"
        outside.write_bytes((src / "background.png").read_bytes())
        (src / "background.png").unlink()
        (src / "background.png").symlink_to(outside)
        with self.assertRaisesRegex(cr.RescueError, "linked path"):
            cr.look_preview(self.cfg, self.stick, cr.LOOK_DEFAULT, self.tmp / "preview.png")

    def test_changed_app_cache_cannot_be_synced_or_packed(self):
        self.fetch()
        self.sync()
        entry = cr.load_lock(self.cfg)["sysinternals"]
        source = self.cfg.cache / "sysinternals" / entry["final"]
        source.write_bytes(fixtures.zipped({"procexp64.exe": b"corrupt executable"}))
        with self.assertRaisesRegex(cr.RescueError, "cached app checksum changed"):
            self.sync()
        self.assertEqual((self.stick / "Apps/sysinternals/procexp64.exe").read_bytes(), b"MZ procexp")
        with self.assertRaisesRegex(cr.RescueError, "cached app checksum changed"):
            fixtures.TestPack.pack(self)
        self.assertFalse((self.tmp / "pack.zip").exists())


class TestVmDiskState(unittest.TestCase):
    def test_transfer_disk_requires_positive_off_or_absent_state(self):
        script = (fixtures.ROOT / "pe/vm/build-vm.sh").read_text()
        helpers = script[script.index("disk_idle() {"):script.index("need_xfer()")]
        for state, status, names, listing_status, allowed in (
            ("shut off", 0, "vm", 0, True), ("running", 0, "vm", 0, False),
            ("paused", 0, "vm", 0, False), ("pmsuspended", 0, "vm", 0, False),
            ("in shutdown", 0, "vm", 0, False), ("", 1, "", 0, True),
            ("", 1, "vm", 0, False), ("", 1, "", 1, False),
            ("shut off", 0, "", 0, False),  # managed save: absent from --without-managed-save
            ("shut off", 0, "", 1, False), # failed saved-state check
        ):
            with self.subTest(state=state, status=status, names=names, listing_status=listing_status):
                result = subprocess.run(["bash", "-c", helpers + '''
VM=vm
die() { exit 9; }
virsh_() {
  if [[ $1 == domstate ]]; then printf '%s' "$STATE"; return "$STATUS"; fi
  printf '%s' "$NAMES"; return "$LISTING_STATUS"
}
need_off
'''], env=dict(os.environ, STATE=state, STATUS=str(status), NAMES=names,
                              LISTING_STATUS=str(listing_status)), capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, allowed, result.stderr)
