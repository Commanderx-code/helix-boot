"""Tests for windows/helix_boot.py with PowerShell and Ventoy faked, so they run anywhere."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("helix_boot", ROOT / "windows" / "helix_boot.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

SYSTEM = {"Number": 0, "Name": "Samsung SSD 990", "Size": 1_000_204_886_016, "Bus": "NVMe", "System": True,
          "Labels": ["", "Windows"], "Letters": ["C"], "Ventoy": ""}
USB_HDD = {"Number": 1, "Name": "WD Elements", "Size": 2_000_398_934_016, "Bus": "SATA", "System": False,
           "Labels": ["Backup"], "Letters": ["D"], "Ventoy": ""}
STICK = {"Number": 2, "Name": "SanDisk Ultra", "Size": 32_010_928_128, "Bus": "USB", "System": False,
         "Labels": ["STICK"], "Letters": ["E"], "Ventoy": ""}
VENTOY = {**STICK, "Labels": ["Ventoy", "VTOYEFI"], "Letters": ["E"], "Ventoy": "E"}
RENAMED = {**STICK, "Labels": ["HelixBoot", "VTOYEFI"], "Letters": ["E", "F"], "Ventoy": "E"}   # renamed in Explorer


def ps(*disks):
    return lambda script: json.dumps(list(disks) if len(disks) != 1 else disks[0])


class TestDisks(unittest.TestCase):
    def test_only_usb_non_system_disks_are_offered(self):
        found = app.usb_disks(ps(SYSTEM, USB_HDD, STICK))
        self.assertEqual([d["Number"] for d in found], [2])
        self.assertFalse(found[0]["IsVentoy"])

    def test_single_disk_and_empty_output(self):
        self.assertEqual(len(app.usb_disks(ps(STICK))), 1)   # PowerShell emits an object, not a list
        self.assertEqual(app.usb_disks(lambda s: ""), [])

    def test_ventoy_detected(self):
        self.assertTrue(app.usb_disks(ps(VENTOY))[0]["IsVentoy"])

    def test_a_renamed_stick_is_still_a_ventoy_stick(self):
        d = app.usb_disks(ps(RENAMED))[0]                    # known by VTOYEFI, not by the data partition's name
        self.assertTrue(d["IsVentoy"])
        self.assertEqual(d["Ventoy"], "E")
        self.assertIn("-eq 'VTOYEFI'", app.DISKS_PS)         # the script falls back to it …
        self.assertIn("Sort-Object Size -Descending", app.DISKS_PS)   # … and takes the biggest other volume

    def test_pick_refuses_system_and_non_usb(self):
        run = ps(SYSTEM, USB_HDD, STICK)
        with self.assertRaisesRegex(app.RescueError, "running Windows"):
            app.pick(0, run)
        with self.assertRaisesRegex(app.RescueError, "isn't a USB"):
            app.pick(1, run)
        with self.assertRaisesRegex(app.RescueError, "no disk 7"):
            app.pick(7, run)
        self.assertEqual(app.pick(2, run)["Name"], "SanDisk Ultra")


class TestVentoy(unittest.TestCase):
    def setUp(self):
        self.vdir = Path(tempfile.mkdtemp())
        (self.vdir / "Ventoy2Disk.exe").write_bytes(b"MZ")

    def test_command_line(self):
        with mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86"}):
            args = app.ventoy_command(self.vdir, "/I", 3, gpt=True, secure_boot=False)
        self.assertEqual(args[1:], ["VTOYCLI", "/I", "/PhyDrive:3", "/GPT", "/NoSB"])
        with mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86"}):
            self.assertEqual(app.ventoy_command(self.vdir, "/U", 3)[1:], ["VTOYCLI", "/U", "/PhyDrive:3"])

    def test_x64_build_is_used_from_the_top_folder(self):
        (self.vdir / "altexe").mkdir()
        (self.vdir / "altexe/Ventoy2Disk_X64.exe").write_bytes(b"MZ64")
        with mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "AMD64"}):
            args = app.ventoy_command(self.vdir, "/I", 1)
        self.assertEqual(Path(args[0]).name, "Ventoy2Disk_X64.exe")
        self.assertEqual((self.vdir / "Ventoy2Disk_X64.exe").read_bytes(), b"MZ64")

    def fake(self, result: str, log: str = "") -> list[str]:
        script = self.vdir / "fake_ventoy.py"
        script.write_text(textwrap.dedent(f"""
            import time
            from pathlib import Path
            for p in (10, 60):
                Path("cli_percent.txt").write_text(str(p)); time.sleep(0.6)
            Path("cli_log.txt").write_text({log!r})
            Path("cli_done.txt").write_text({result!r})
        """))
        return [sys.executable, str(script)]

    def test_success_reports_progress(self):
        seen = []
        app.run_ventoy(self.fake("0"), self.vdir, seen.append)
        self.assertEqual(seen[-1], 100)
        self.assertTrue(any(0 < p < 100 for p in seen), seen)

    def test_failure_shows_the_log(self):
        with self.assertRaisesRegex(app.RescueError, "(?s)cli_done.txt: 1.*disk is write-protected"):
            app.run_ventoy(self.fake("1", "line\ndisk is write-protected\n"), self.vdir)

    def test_crash_without_result(self):
        with self.assertRaisesRegex(app.RescueError, "missing"):
            app.run_ventoy([sys.executable, "-c", "import sys; sys.exit(3)"], self.vdir)


class TestFlows(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.vdir = Path(tempfile.mkdtemp())
        patches = [
            mock.patch.object(app, "config", lambda: "cfg"),
            mock.patch.object(app, "fetch", lambda cfg, tools=(): self.calls.append("fetch") or True),
            mock.patch.object(app, "ventoy_dir", lambda cfg: self.vdir),
            mock.patch.object(app, "sync", lambda cfg, target, init: self.calls.append(("sync", target, init))),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def ventoy(self, args, vdir, progress):
        self.calls.append(("ventoy", args[1:]))

    def test_install(self):
        states = iter([ps(STICK), ps(VENTOY)])                 # before, then after Ventoy
        current = {"run": next(states)}

        def run(script):
            return current["run"](script)

        def ventoy(args, vdir, progress):
            self.ventoy(args, vdir, progress)
            current["run"] = next(states)

        with redirect_stdout(io.StringIO()), mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86"}):
            letter = app.install(2, secure_boot=True, run=run, ventoy=ventoy)
        self.assertEqual(letter, "E:\\")
        self.assertEqual(self.calls, ["fetch", ("ventoy", ["VTOYCLI", "/I", "/PhyDrive:2", "/GPT"]),
                                      ("sync", "E:\\", True)])

    def test_install_refuses_the_system_disk_before_anything(self):
        with self.assertRaises(app.RescueError):
            app.install(0, run=ps(SYSTEM, STICK), ventoy=self.ventoy)
        self.assertEqual(self.calls, [])

    def test_update_keeps_files_and_needs_ventoy(self):
        with self.assertRaisesRegex(app.RescueError, "doesn't have Ventoy"):
            app.update(2, run=ps(STICK), ventoy=self.ventoy)
        with redirect_stdout(io.StringIO()):
            app.update(2, run=ps(VENTOY), ventoy=self.ventoy)
        self.assertEqual(self.calls, ["fetch", ("sync", "E:\\", False)])      # no Ventoy step by default

    def pack_flow(self):
        self.pack = Path(tempfile.mkdtemp()) / "helix-boot-2026-09-29.zip"
        for name, fake in (("pack_ventoy_dir", lambda cfg, pack: self.calls.append(("pack-ventoy", pack)) or self.vdir),
                           ("unpack", lambda cfg, target, pack, init: self.calls.append(("unpack", target, init)))):
            patcher = mock.patch.object(app, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_install_from_a_pack_downloads_nothing(self):
        self.pack_flow()
        states = iter([ps(STICK), ps(VENTOY)])
        current = {"run": next(states)}

        def ventoy(args, vdir, progress):
            self.ventoy(args, vdir, progress)
            current["run"] = next(states)

        with redirect_stdout(io.StringIO()), mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86"}):
            app.install(2, run=lambda s: current["run"](s), ventoy=ventoy, pack=self.pack)
        self.assertEqual(self.calls, [("pack-ventoy", self.pack), ("ventoy", ["VTOYCLI", "/I", "/PhyDrive:2", "/GPT"]),
                                      ("unpack", "E:\\", True)])

    def test_update_from_a_pack(self):
        self.pack_flow()
        with redirect_stdout(io.StringIO()), mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86"}):
            app.update(2, run=ps(VENTOY), ventoy=self.ventoy, pack=self.pack)
            self.assertEqual(self.calls, [("unpack", "E:\\", False)])
            self.calls.clear()
            app.update(2, run=ps(VENTOY), ventoy=self.ventoy, pack=self.pack, upgrade_ventoy=True)
        self.assertEqual(self.calls, [("pack-ventoy", self.pack), ("ventoy", ["VTOYCLI", "/U", "/PhyDrive:2"]),
                                      ("unpack", "E:\\", False)])

    def test_linux_only_pack_is_refused_before_the_disk_is_touched(self):
        pack = Path(tempfile.mkdtemp()) / "old.zip"
        with zipfile.ZipFile(pack, "w") as zf:
            zf.writestr(app.cr.PACK_META, json.dumps({
                "format": app.cr.PACK_FORMAT, "isos": [], "apps": {}, "trees": [],
                "ventoy": {"file": "installer/ventoy-1.1.17-linux.tar.gz", "version": "1.1.17"}}))
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(app.cr.RescueError, "Ventoy for Linux only"):
            app.install(2, run=ps(STICK), ventoy=self.ventoy, pack=pack)
        self.assertEqual(self.calls, [])

    def test_cli_install_needs_yes(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out), \
                mock.patch.object(app, "open_log", lambda p: None), mock.patch.object(sys, "__stdout__", out):
            self.assertEqual(app.cli(["--install", "2"]), 1)
        self.assertIn("--yes", out.getvalue())

    def test_cli_look_goes_to_the_engine(self):
        seen = {}
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out), mock.patch.object(app, "open_log", lambda p: None), \
                mock.patch.object(sys, "__stdout__", out), \
                mock.patch.object(app.cr, "cmd_theme", lambda cfg, a: seen.update(vars(a)) or 0), \
                mock.patch.object(app, "look_window", lambda mnt, **kw: seen.update(window=str(mnt))):
            self.assertEqual(app.cli(["--look", "E:\\", "--theme", "midnight", "--icons", "off"]), 0)
            self.assertEqual((seen["stick"], seen["theme"], seen["icons"], seen["reset"]), ("E:\\", "midnight", "off", False))
            self.assertNotIn("window", seen)
            self.assertEqual(app.cli(["--look", "E:\\"]), 0)           # no options: the Look window
            self.assertEqual(seen["window"], "E:\\")
        # every option `helix theme` takes is passed, so the engine never misses one
        self.assertEqual(set(seen) - {"window"}, {"stick", "theme", "icons", "background", "dim", "splash", "reset",
                                                  "preview", "menu", "json"})


class TestFindPack(unittest.TestCase):
    def make(self, path: Path, meta: str | None = "helix-boot-pack.json") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(meta or "something-else.txt", "{}")
        return path

    def test_pack_beside_the_app(self):
        here = Path(tempfile.mkdtemp())
        self.make(here / "photos.zip", meta=None)             # a zip that isn't a pack
        self.assertIsNone(app.find_pack(here))
        pack = self.make(here / "helix-boot-2026-09-29.zip")
        self.assertEqual(app.find_pack(here), pack)
        old = self.make(here / "commander-rescue-2026-09-20.zip", meta="commander-rescue-pack.json")
        os.utime(old, (1, 1))
        self.assertEqual(app.find_pack(here), pack)            # the newest one

    def test_pack_beside_the_installer_folder(self):
        top = Path(tempfile.mkdtemp())
        pack = self.make(top / "helix-boot-2026-09-29.zip")    # unzipped: installer\HelixBoot.exe
        (top / "installer").mkdir()
        self.assertEqual(app.find_pack(top / "installer"), pack)
        self.assertIsNone(app.find_pack(top / "elsewhere"))


class TestConsole(unittest.TestCase):
    def test_starts_from_explorer_without_a_console(self):
        # Double-clicked, the windowed .exe has sys.stdout/stderr = None; loading the app and
        # helix inside it used to crash on stdout.isatty()
        with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            s = importlib.util.spec_from_file_location("helix_boot_noconsole", ROOT / "windows" / "helix_boot.py")
            mod = importlib.util.module_from_spec(s)
            s.loader.exec_module(mod)
            self.assertIsNotNone(sys.stdout)
            print("printing works")
        self.assertFalse(mod.cr.C.on)

    def test_cp1252_console_does_not_crash(self):
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp1252", write_through=True)
        with mock.patch.object(sys, "__stdout__", console), mock.patch.object(app, "open_log", lambda p: None), \
                mock.patch.object(app, "config", lambda: "cfg"), \
                mock.patch.object(app, "fetch", lambda cfg, tools=(): print("✓ Ventoy 1.1.17 — verified") or True):
            self.assertEqual(app.cli(["--fetch", "ventoy"]), 0)
        self.assertIn(b"? Ventoy 1.1.17 \x97 verified", raw.getvalue())  # ✓ has no cp1252 byte; — does

    def test_unexpected_error_is_logged_not_raised(self):
        log = io.StringIO()
        log.close = lambda: None
        with mock.patch.object(app, "cli", mock.Mock(side_effect=RuntimeError("boom"))), \
                mock.patch.object(app, "open_log", lambda p: log), mock.patch.object(sys, "argv", ["x", "--list"]), \
                mock.patch.object(sys, "__stderr__", io.StringIO()):
            self.assertEqual(app.main(), 1)
        self.assertIn("RuntimeError: boom", log.getvalue())


class TestPackaging(unittest.TestCase):
    def test_app_names_every_module_helix_imports(self):
        # PyInstaller can't see inside helix (it's a data file), so the app imports them for it.
        import ast

        def imported(path):
            mods = set()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    mods |= {a.name for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods.add(node.module)
            return mods - {"__future__"}

        optional = {"PIL"}   # the splash's loading bar; packs from Linux already carry its frames
        missing = imported(ROOT / "helix") - imported(ROOT / "windows" / "helix_boot.py") - optional
        self.assertEqual(sorted(missing), [], "add these imports to windows/helix_boot.py")


if __name__ == "__main__":
    unittest.main()
