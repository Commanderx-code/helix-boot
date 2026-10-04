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
STICK = {"Number": 2, "Name": "SanDisk Ultra", "Serial": "test-usb-123", "Size": 32_010_928_128, "Bus": "USB", "System": False,
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
            mock.patch.object(app, "update_summary", lambda cfg, target, pack=None: "Copy 1 (1.0 GiB): Clonezilla 3.3"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def ventoy(self, args, vdir, progress):
        self.calls.append(("ventoy", args[1:]))

    def test_install_binds_the_gui_selection_before_fetching(self):
        with self.assertRaisesRegex(app.RescueError, "replaced"):
            app.install(2, run=ps({**STICK, "Serial": "other"}), expected=STICK, ventoy=self.ventoy)
        self.assertEqual(self.calls, [])

    def test_install_refuses_replacement_during_download(self):
        current = dict(STICK)
        def fetch(cfg):
            current["Serial"] = "replacement"
            return True
        with mock.patch.object(app, "fetch", fetch), self.assertRaisesRegex(app.RescueError, "replaced"):
            app.install(2, run=lambda script: json.dumps(current), ventoy=self.ventoy)
        self.assertEqual(self.calls, [])

    def test_update_refuses_changes_during_confirmation(self):
        for changed in ({"Serial": "replacement"}, {"System": True}, {"Ventoy": "G"}):
            with self.subTest(changed=changed):
                current = dict(VENTOY)
                def confirm(summary):
                    current.update(changed)
                    return True
                self.calls.clear()
                with redirect_stdout(io.StringIO()), self.assertRaises(app.RescueError):
                    app.update(2, run=lambda script: json.dumps(current), ventoy=self.ventoy, confirm=confirm)
                self.assertEqual(self.calls, ["fetch"])

    def test_install_refuses_replacement_after_ventoy_before_copying(self):
        current = dict(STICK)
        def ventoy(*args):
            current.update(VENTOY, Serial="replacement")
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(app.RescueError, "replaced"):
            app.install(2, run=lambda script: json.dumps(current), ventoy=ventoy)
        self.assertEqual(self.calls, ["fetch"])

    def test_missing_hardware_identity_refuses_writes(self):
        with self.assertRaisesRegex(app.RescueError, "nothing that identifies this disk"):
            app.install(2, run=ps({**STICK, "Serial": ""}), ventoy=self.ventoy)
        self.assertEqual(self.calls, [])

    def test_a_stick_without_a_serial_is_known_by_its_device_id(self):
        # Many sticks report no serial. The id Windows gave this one when it was plugged in tells
        # it from another that takes its place, so it can be written, and a swap is still caught.
        bare = {**STICK, "Serial": "", "Id": "USBSTOR\\DISK&VEN_X\\7&2A3B&0", "Path": "\\\\?\\usbstor#disk&ven_x#7&2a3b&0"}
        self.assertEqual(app.disk_identity(bare)[:2], ("Id", bare["Id"]))
        self.assertEqual(app.disk_identity({**bare, "Id": ""})[:2], ("Path", bare["Path"]))
        self.assertEqual(app.disk_identity(STICK)[:2], ("Serial", "test-usb-123"))        # a serial comes first
        with self.assertRaisesRegex(app.RescueError, "replaced"):
            app.recheck_disk(bare, run=ps({**bare, "Id": "USBSTOR\\DISK&VEN_X\\7&9999&0"}))
        self.assertEqual(app.recheck_disk(bare, run=ps(bare))["Number"], 2)

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
        self.assertEqual(self.calls, ["fetch", ("sync", "E:\\", True)])       # no Ventoy step by default

    def test_update_says_what_it_will_do_and_can_be_called_off(self):
        shown = []
        with redirect_stdout(io.StringIO()) as out, self.assertRaisesRegex(app.RescueError, "nothing on the stick was changed"):
            app.update(2, run=ps(VENTOY), ventoy=self.ventoy, confirm=lambda summary: shown.append(summary))   # "no"
        self.assertEqual(shown, ["Copy 1 (1.0 GiB): Clonezilla 3.3"])
        self.assertIn("This update will:", out.getvalue())
        self.assertEqual(self.calls, ["fetch"])                               # asked before the stick is touched
        self.calls.clear()
        with redirect_stdout(io.StringIO()):
            app.update(2, run=ps(RENAMED), ventoy=self.ventoy, confirm=lambda summary: True)
        self.assertEqual(self.calls, ["fetch", ("sync", "E:\\", True)])     # checked to be Ventoy: any name will do

    def test_a_new_stick_gets_its_name(self):
        ran = []
        with redirect_stdout(io.StringIO()) as out:
            app.name_stick("E:\\", "HelixBoot", run=ran.append)
            app.name_stick("E:\\", "Ventoy", run=ran.append)                # Ventoy's own name: nothing to do
            app.name_stick("E:\\", "bad'; Format-Volume", run=ran.append)   # never reaches PowerShell
        self.assertEqual(ran, ["Set-Volume -DriveLetter E -NewFileSystemLabel 'HelixBoot'"])
        self.assertIn("Stick named HelixBoot", out.getvalue())

        def refuses(script):
            raise app.cr.RescueError("access denied")
        with redirect_stdout(io.StringIO()) as out:
            app.name_stick("E:\\", "HelixBoot", run=refuses)                # not worth failing an install over
        self.assertIn("couldn't name the stick", out.getvalue())

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
            self.assertEqual(self.calls, [("unpack", "E:\\", True)])
            self.calls.clear()
            app.update(2, run=ps(VENTOY), ventoy=self.ventoy, pack=self.pack, upgrade_ventoy=True)
        self.assertEqual(self.calls, [("pack-ventoy", self.pack), ("ventoy", ["VTOYCLI", "/U", "/PhyDrive:2"]),
                                      ("unpack", "E:\\", True)])

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
                                                  "preview", "menu", "json", "export", "import_"})

    def test_the_update_notice_can_be_switched_off(self):
        asked = []
        found = {"checked": "2026-10-03T10:00", "fetched": 3, "failed": 0, "newer": [{"title": "SystemRescue"}]}
        cfg = mock.Mock(settings={})
        with mock.patch.object(app.cr, "tool_updates", lambda c, refresh=False: asked.append(refresh) or found):
            self.assertIn("Newer versions of 1 tool(s) are out: SystemRescue", app.updates_notice(cfg, True))
            cfg.settings = {"check_for_updates": False}
            self.assertIn("check_for_updates = false", app.updates_notice(cfg))
        self.assertEqual(asked, [True])               # switched off: nothing is asked of any site

    def test_boot_script_is_changed_like_on_linux(self):
        with tempfile.TemporaryDirectory() as tmp:
            efi, stick = Path(tmp) / "efi", Path(tmp) / "stick"
            (efi / "grub").mkdir(parents=True)
            (stick / app.cr.STATE_DIR).mkdir(parents=True)
            script = efi / "grub" / "grub.cfg"
            script.write_bytes(b"function legacy_iso_memdisk {\n}\nfunction uefi_iso_memdisk {\n}\n"   # LF, as Ventoy's is
                               b'set VTOY_HELP_CMD="x"\nset VTOY_LANG_CMD="y"\n'
                               b"#clear all input key before show main menu\nvt_clear_key\n")
            asked = []
            run = lambda ps: asked.append(ps) or f"{efi}\n"                       # noqa: E731
            cfg = mock.Mock(settings={"theme": "theme"})
            with redirect_stdout(io.StringIO()) as out, mock.patch.object(app, "config", lambda: cfg), \
                    mock.patch.object(app.cr, "_apply_look"), mock.patch.object(app.cr, "_flush_volume"):
                self.assertTrue(app.boot_script(str(stick), disk_no=3, run=run))
                self.assertIn("-DiskNumber 3", asked[0])
                self.assertIn(app.cr.SPLASH_BEGIN, script.read_text(encoding="utf-8"))
                self.assertTrue((stick / app.cr.KEYS_HOOK).is_file())
                self.assertIn("L opens the power menu", out.getvalue())
                # Windows doesn't show Ventoy's partition: nothing fails, and the stick is told the keys are Ventoy's
                self.assertFalse(app.boot_script(str(stick), disk_no=3, run=lambda ps: "\n"))
                self.assertIn("stay Ventoy's Language and Help", out.getvalue())
                self.assertFalse((stick / app.cr.KEYS_HOOK).exists())

    def test_changed_apps_fail_windows_verification(self):
        found = dict(damaged=[], missing=[], menu=None, changed={"app": ["app.exe"]})
        with redirect_stdout(io.StringIO()), mock.patch.object(app.cr, "check_stick", return_value=found), \
             mock.patch.object(app.cr, "check_text", return_value="changed app"), \
             self.assertRaisesRegex(app.RescueError, "changed app"):
            app.check("E:\\")

    def test_check_stick(self):
        good = {"damaged": [], "missing": [], "changed": {}, "checked": 9, "unrecorded": [], "images": 3,
                "apps": 2, "menu": None}
        bad = {**good, "damaged": ["ISO/2-Rescue/x.iso"]}
        seen = []
        for found, fails in ((good, False), (bad, True)):
            with redirect_stdout(io.StringIO()), \
                    mock.patch.object(app.cr, "check_stick", lambda mnt, hook=None, f=found: seen.append(hook) or f):
                if fails:
                    with self.assertRaisesRegex(app.RescueError, "1 boot image\\(s\\) are damaged"):
                        app.check("E:\\", progress=print)
                else:
                    self.assertIn("Everything checks out", app.check("E:\\", progress=print))
        self.assertEqual(seen, [print, print])        # the window's progress bar follows the reading


class TestPreview(unittest.TestCase):
    def test_preview_uses_the_same_verification_as_update(self):
        with mock.patch.object(app.cr, "update_plan", return_value=[]) as plan:
            app.update_summary("cfg", "E:\\")
        plan.assert_called_once_with("cfg", "E:\\", None, init=True, verify=True)


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

        optional = {"PIL"}   # previews, your own pictures, the splash's loading bar: fine without
        missing = imported(ROOT / "helix") - imported(ROOT / "windows" / "helix_boot.py") - optional
        self.assertEqual(sorted(missing), [], "add these imports to windows/helix_boot.py")


if __name__ == "__main__":
    unittest.main()
