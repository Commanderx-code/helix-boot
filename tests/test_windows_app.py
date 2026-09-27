"""Tests for windows/commander_rescue.py with PowerShell and Ventoy faked, so they run anywhere."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("commander_rescue", ROOT / "windows" / "commander_rescue.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

SYSTEM = {"Number": 0, "Name": "Samsung SSD 990", "Size": 1_000_204_886_016, "Bus": "NVMe", "System": True,
          "Labels": ["", "Windows"], "Letters": ["C"], "Ventoy": ""}
USB_HDD = {"Number": 1, "Name": "WD Elements", "Size": 2_000_398_934_016, "Bus": "SATA", "System": False,
           "Labels": ["Backup"], "Letters": ["D"], "Ventoy": ""}
STICK = {"Number": 2, "Name": "SanDisk Ultra", "Size": 32_010_928_128, "Bus": "USB", "System": False,
         "Labels": ["STICK"], "Letters": ["E"], "Ventoy": ""}
VENTOY = {**STICK, "Labels": ["Ventoy", "VTOYEFI"], "Letters": ["E"], "Ventoy": "E"}


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

    def test_cli_install_needs_yes(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out), \
                mock.patch.object(app, "open_log", lambda p: None), mock.patch.object(sys, "__stdout__", out):
            self.assertEqual(app.cli(["--install", "2"]), 1)
        self.assertIn("--yes", out.getvalue())


if __name__ == "__main__":
    unittest.main()
