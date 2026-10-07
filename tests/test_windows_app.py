"""Tests for windows/helix_boot.py with PowerShell and Ventoy faked, so they run anywhere."""
import hashlib
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
            mock.patch.object(app, "update_summary", lambda cfg, target, pack=None, **kw: "Copy 1 (1.0 GiB): Clonezilla 3.3"),
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

    def test_install_can_test_the_stick_first_and_stops_on_a_bad_one(self):
        def flow():
            states = iter([ps(STICK), ps(VENTOY)])
            current = {"run": next(states)}

            def ventoy(args, vdir, progress):
                self.ventoy(args, vdir, progress)
                current["run"] = next(states)
            return (lambda script: current["run"](script)), ventoy

        good = {"asked": 1 << 30, "written": 1 << 30, "bad": [], "pieces": 1, "error": None, "seconds": 61}
        for found, fails in ((good, False), ({**good, "bad": [0]}, True)):
            self.calls.clear()
            run, ventoy = flow()
            watch = app.cr.Progress.watch = object()                # the byte counter is put back afterwards
            with redirect_stdout(io.StringIO()), mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86"}), \
                    mock.patch.object(app.cr, "test_stick",
                                      lambda mnt, hook=None, f=found: self.calls.append(("test", str(mnt))) or f):
                try:
                    if fails:
                        with self.assertRaisesRegex(app.RescueError, "read back wrong"):
                            app.install(2, run=run, ventoy=ventoy, test=True)
                    else:
                        app.install(2, run=run, ventoy=ventoy, test=True)
                    self.assertIs(app.cr.Progress.watch, watch)
                finally:
                    app.cr.Progress.watch = None
            self.assertEqual(self.calls[:3], ["fetch", ("ventoy", ["VTOYCLI", "/I", "/PhyDrive:2", "/GPT"]),
                                              ("test", "E:\\")])
            self.assertEqual(("sync", "E:\\", True) in self.calls, not fails)   # a stick that fails stays empty

    def test_repair_runs_chkdsk_and_reads_its_answer(self):
        ran = []
        for code, said in ((0, "found nothing wrong"), (1, "had errors and Windows repaired them")):
            with redirect_stdout(io.StringIO()):
                text = app.repair("E:\\", run=lambda cmd, c=code: ran.append(cmd) or (c, "Windows has scanned\r\n\r\n"))
            self.assertIn(said, text)
        self.assertEqual(ran[0][1:], ["E:", "/f", "/x"])
        self.assertEqual(ran[0][0].lower().replace("\\", "/").rsplit("/", 1)[-1], "chkdsk.exe")
        if os.name == "nt":                                     # (the real one, by its full path)
            self.assertTrue(os.path.isabs(ran[0][0]) and os.path.isfile(ran[0][0]), ran[0][0])
        # On Windows it is run by its full path in the system folder, never looked up by name
        system32 = self.vdir / "System32"
        system32.mkdir()
        (system32 / "chkdsk.exe").write_bytes(b"MZ")
        self.assertEqual(app.system_tool("chkdsk.exe", folder=str(system32)), str(system32 / "chkdsk.exe"))
        with self.assertRaisesRegex(app.RescueError, "is missing from Windows"):
            app.system_tool("nothere.exe", folder=str(system32))
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(app.RescueError, "couldn't repair E:"):
            app.repair("E:", run=lambda cmd: (3, "Cannot open volume for direct access."))
        with self.assertRaisesRegex(app.RescueError, "isn't a drive letter"):
            app.repair("\\\\server\\share")

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

    def test_the_engine_reports_each_chunk_copied(self):
        seen = []
        app.cr.Progress.watch = lambda n, label: seen.append((n, label))
        try:
            p = app.cr.Progress()
            p.file("(1/2) memtest.iso", 10)
            p.add(4)
            p.add(6)
        finally:
            app.cr.Progress.watch = None
        self.assertEqual(seen, [(4, "(1/2) memtest.iso"), (6, "(1/2) memtest.iso")])
        app.cr.Progress().add(1)                      # nobody watching: nothing happens

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
    def test_an_updates_size_reaches_the_window(self):
        plan = [("copy", "Clonezilla 3.3", 3 << 30), ("copy", "Sysinternals", 50 << 20), ("remove", "old.iso", 0),
                ("keep", "paid.iso", 0)]
        self.assertEqual(app.copy_bytes(plan), (3 << 30) + (50 << 20))
        told = []
        with mock.patch.object(app.cr, "update_plan", return_value=plan):
            text = app.update_summary("cfg", "E:\\", on_plan=told.append)
        self.assertEqual(told, [(3 << 30) + (50 << 20)])
        self.assertIn("Clonezilla 3.3", text)

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


class TestWords(unittest.TestCase):
    def test_the_window_knows_the_engines_words_about_newer_tools(self):
        found = {"fetched": 3, "checked": "2026-10-07T12:22", "failed": 0,
                 "newer": [{"name": "x", "title": "X", "have": "1", "latest": "2"}]}
        self.assertIn(app.GETS_THEM, app.cr.updates_text(found))        # (the window rewords it when a pack is chosen)


class TestSelfUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = mock.Mock(cache=self.tmp / "cache", settings={})
        self.cfg.cache.mkdir()
        p = mock.patch.object(app, "config", lambda: self.cfg)
        p.start()
        self.addCleanup(p.stop)

    def latest(self, tag):
        return mock.patch.object(app.cr, "_latest_tag", lambda repo: tag)

    def test_asks_where_the_latest_release_is_and_remembers_for_a_while(self):
        newer = f"v{app.cr.__version__.rsplit('.', 1)[0]}.999"
        with self.latest(newer):
            found = app.cr.app_update(self.cfg)
        self.assertEqual((found["current"], found["latest"], found["newer"]), (app.cr.__version__, newer[1:], True))
        with mock.patch.object(app.cr, "_latest_tag", side_effect=AssertionError("asked again too soon")):
            self.assertTrue(app.cr.app_update(self.cfg)["newer"])          # from the last look
        with self.latest(f"v{app.cr.__version__}"):
            self.assertFalse(app.cr.app_update(self.cfg, refresh=True)["newer"])
        with self.latest("v0.0.1"):
            self.assertFalse(app.cr.app_update(self.cfg, refresh=True)["newer"])    # never offered an older one
        with self.latest(None):                                             # offline: says so when asked by hand
            with self.assertRaisesRegex(app.cr.RescueError, "couldn't ask GitHub"):
                app.cr.app_update(self.cfg, refresh=True)
            self.assertEqual(app.cr.app_update(self.cfg)["latest"], "0.0.1")       # and otherwise keeps what it knew
        with self.latest("not-a-version/../x"):
            with self.assertRaisesRegex(app.cr.RescueError, "couldn't ask GitHub"):
                app.cr.app_update(self.cfg, refresh=True)

    def test_turned_off_in_local_toml_and_a_declined_version_is_remembered(self):
        self.cfg.settings = {"check_for_updates": False}
        with mock.patch.object(app.cr, "_latest_tag", side_effect=AssertionError("it was turned off")):
            self.assertIsNone(app.app_news(self.cfg))
        with self.latest("v99.0.0"):
            self.assertTrue(app.app_news(self.cfg, refresh=True)["newer"])   # asked for by hand: still answers
            app.cr.app_decline(self.cfg, "99.0.0")
            self.assertEqual(app.cr.app_update(self.cfg)["declined"], "99.0.0")

    def test_the_new_program_takes_the_running_ones_place(self):
        me, new = self.tmp / "HelixBoot.exe", self.tmp / "download.exe"
        me.write_bytes(b"MZ old")
        new.write_bytes(b"MZ new")
        said = io.StringIO()
        with self.latest("v99.0.0"), mock.patch.object(app.cr, "fetch_app", lambda cfg, asset: (new, "99.0.0", hashlib.sha256(b"MZ new").hexdigest())), \
                redirect_stdout(said):
            text = app.self_update(me=me)
        self.assertIn("Helix Boot 99.0.0 is in place", text)
        self.assertEqual(me.read_bytes(), b"MZ new")
        self.assertEqual((self.tmp / "HelixBoot.old.exe").read_bytes(), b"MZ old")     # stepped aside, deleted at next start
        self.assertFalse((self.tmp / "HelixBoot.exe.new").exists())
        if os.name != "nt":
            self.assertTrue(os.access(me, os.X_OK))
        with mock.patch.object(app, "FROZEN", True), mock.patch.object(app.sys, "executable", str(me)):
            app.tidy_old_program()
        self.assertFalse((self.tmp / "HelixBoot.old.exe").exists())

    def test_nothing_is_replaced_when_there_is_nothing_newer_or_the_download_isnt(self):
        me, new = self.tmp / "HelixBoot.exe", self.tmp / "download.exe"
        me.write_bytes(b"MZ old")
        new.write_bytes(b"MZ what")
        with self.latest(f"v{app.cr.__version__}"), \
                mock.patch.object(app.cr, "fetch_app", side_effect=AssertionError("nothing to download")):
            self.assertIn("is the newest version", app.self_update(me=me))
        with self.latest("v99.0.0"), redirect_stdout(io.StringIO()):
            with mock.patch.object(app.cr, "fetch_app", lambda cfg, asset: (new, app.cr.__version__, "0" * 64)):
                with self.assertRaisesRegex(app.RescueError, "isn't newer than this one"):
                    app.self_update(me=me)
            with mock.patch.object(app, "FROZEN", False):               # from a clone: git pull, nothing swapped
                with self.assertRaisesRegex(app.RescueError, "git pull"):
                    app.self_update()
        self.assertEqual(me.read_bytes(), b"MZ old")

    def release(self, content=b"MZ new program", asset="HelixBoot-linux-x86_64", digest=None, url=None):
        digest = digest if digest is not None else "sha256:" + hashlib.sha256(content).hexdigest()
        url = url or f"{app.cr.GITHUB_WEB}/{app.cr.APP_REPO}/releases/download/v99.0.0/{asset}"
        return json.dumps({"tag_name": "v99.0.0", "assets": [{"name": asset, "digest": digest,
                                                             "browser_download_url": url}]}).encode()

    def fetch(self, served=b"MZ new program", **rel):
        asked, got = [], []

        def download(url, dest):
            got.append(url)
            dest.write_bytes(served)
        with mock.patch.object(app.cr, "http_get", lambda url, *a, **k: asked.append(url) or self.release(**rel)), \
                mock.patch.object(app.cr, "download", download), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                return app.cr.fetch_app(self.cfg, rel.get("asset", "HelixBoot-linux-x86_64")), asked, got
            except app.cr.RescueError as e:
                return e, asked, got

    def test_the_download_is_what_github_says_it_is_now_whatever_the_cache_holds(self):
        (f, version, sha), asked, got = self.fetch()
        self.assertEqual((f.name, version, f.read_bytes()), ("HelixBoot-linux-x86_64", "99.0.0", b"MZ new program"))
        self.assertEqual(sha, hashlib.sha256(b"MZ new program").hexdigest())
        self.assertEqual(asked, [f"{app.cr.GITHUB_API}/repos/{app.cr.APP_REPO}/releases/latest"])
        self.assertEqual(len(got), 1)
        _, _, got = self.fetch()                                    # still that file: not downloaded twice
        self.assertEqual(got, [])
        f.write_bytes(b"MZ altered in the cache")                   # changed where it was kept: not believed
        (f, version, sha), _, got = self.fetch()
        self.assertEqual((len(got), f.read_bytes()), (1, b"MZ new program"))

    def test_a_download_that_isnt_githubs_file_is_deleted_and_nothing_else_is_fetched(self):
        failed, _, got = self.fetch(served=b"MZ something else")
        self.assertIn("doesn't have the sha256 GitHub records", str(failed))
        self.assertFalse((self.cfg.cache / "helixboot-update" / "HelixBoot-linux-x86_64").exists())
        for rel, why in ((dict(digest=""), "gives no sha256"), (dict(digest="sha256:abc"), "gives no sha256"),
                         (dict(url="https://example.com/HelixBoot-linux-x86_64"), "gives no sha256"),
                         (dict(asset="HelixBoot.exe"), None)):
            failed, _, got = self.fetch(**rel) if why else self.fetch(asset="HelixBoot.exe")
            if why:
                self.assertIn(why, str(failed))
                self.assertEqual(got, [])                           # nothing unverifiable is even downloaded
        with mock.patch.object(app.cr, "http_get", lambda url, *a, **k: self.release(asset="HelixBoot.exe")):
            with self.assertRaisesRegex(app.cr.RescueError, "has no HelixBoot-linux-x86_64"):
                app.cr.fetch_app(self.cfg, "HelixBoot-linux-x86_64")
        for bad in ("evil.exe", "../HelixBoot.exe", "HelixBoot.exe/x", ""):
            with self.assertRaisesRegex(app.cr.RescueError, "isn't one of Helix Boot's programs"):
                app.cr.fetch_app(self.cfg, bad)

    def test_what_goes_into_place_is_the_verified_copy(self):
        me, new = self.tmp / "HelixBoot.exe", self.tmp / "download.exe"
        me.write_bytes(b"MZ old")
        new.write_bytes(b"MZ swapped after it was checked")
        with self.assertRaisesRegex(app.RescueError, "changed before it could be put in place"):
            app.replace_program(new, me, hashlib.sha256(b"MZ new").hexdigest())
        self.assertEqual(me.read_bytes(), b"MZ old")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir() if p.is_file()), ["HelixBoot.exe", "download.exe"])


class TestEjectAndChoices(unittest.TestCase):
    def test_eject_flushes_asks_windows_and_waits_for_the_drive_to_go(self):
        asked, after = [], {"gone": False}

        def run(script):
            if "InvokeVerb" in script:
                asked.append(script)
                after["gone"] = True
                return ""
            return ps({**VENTOY, "Ventoy": "", "Letters": []} if after["gone"] else VENTOY)(script)
        with mock.patch.object(app.cr, "_flush_volume") as flush, mock.patch.object(app.time, "sleep"):
            text = app.eject({**VENTOY, "IsVentoy": True}, run)
        self.assertIn("E: is ejected: safe to unplug", text)
        self.assertEqual(len(asked), 1)
        self.assertIn("ParseName('E:')", asked[0])
        flush.assert_called_once()
        with mock.patch.object(app.cr, "_flush_volume"), mock.patch.object(app.time, "sleep"):
            with self.assertRaisesRegex(app.RescueError, "wouldn't eject E:"):
                app.eject({**VENTOY, "IsVentoy": True}, ps(VENTOY))            # still there: something has it open
            for letter in ("", "E:\\", "E'; calc; '"):
                with self.assertRaisesRegex(app.RescueError, "no stick's drive letter"):
                    app.eject({**VENTOY, "Ventoy": letter}, lambda s: self.fail("nothing may be run"))

    def test_tools_left_out_for_antivirus_reach_the_engine_and_only_for_that_run(self):
        seen = []
        with mock.patch.object(app.cr, "cmd_sync", lambda cfg, a: seen.append(("sync", a.leave_out)) or 0), \
                mock.patch.object(app.cr, "cmd_unpack", lambda cfg, a: seen.append(("unpack", a.leave_out)) or 0), \
                redirect_stdout(io.StringIO()):
            app.LEAVE_OUT.update({"produkey"})
            try:
                app.sync("cfg", "E:\\", init=True)
                app.unpack("cfg", "E:\\", "pack.zip", init=True)
            finally:
                app.LEAVE_OUT.clear()
            app.sync("cfg", "E:\\", init=False)
        self.assertEqual(seen, [("sync", ["produkey"]), ("unpack", ["produkey"]), ("sync", [])])

    def test_the_shipped_list_flags_only_what_was_seen_to_be_blocked(self):
        cfg = app.cr.Config(repo=ROOT, manifest=ROOT / "tools.toml")
        self.assertEqual([t["title"] for t in app.cr.flagged_tools(cfg)], ["ProduKey"])
        choices = app.cr.tool_choices(cfg)
        self.assertGreater(len(choices), 40)
        self.assertTrue(all(c["category"] and c["title"] for c in choices))



if __name__ == "__main__":
    unittest.main()
