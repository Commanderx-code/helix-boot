"""Tests for linux/helix_gui.py: the Linux parts under the window, with lsblk, udisks, pkexec and
Ventoy faked, so they run anywhere and touch no disk."""
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("helix_gui", ROOT / "linux" / "helix_gui.py")
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)
app = gui.app
gui.on_linux()

GB = 1000**3


def disk(name, tran, size, parts=(), rm=False, vendor="", model="", serial=""):
    return {"name": f"/dev/{name}", "path": f"/dev/{name}", "size": size, "type": "disk", "tran": tran, "rm": rm,
            "model": model, "vendor": vendor, "serial": serial, "label": None, "mountpoints": [None],
            "children": [{"name": f"/dev/{name}{n}", "path": f"/dev/{name}{n}", "size": psize, "type": "part",
                          "label": label, "mountpoints": [mnt] if mnt else [None]}
                         for n, (psize, label, mnt) in enumerate(parts, 1)]}


NVME = disk("nvme0n1", "nvme", 1000 * GB, [(GB, None, "/boot/efi"), (999 * GB, None, "/")], model="Samsung SSD 990")
USB_HDD = disk("sda", "sata", 2000 * GB, [(2000 * GB, "Backup", "/mnt/backup")], model="WD Elements")
PLAIN = disk("sdb", "usb", 32 * GB, [(32 * GB, "STICK", None)], rm=True, vendor="SanDisk ", model="Ultra", serial="S1")
VENTOY = disk("sdb", "usb", 32 * GB, [(32 * GB - 32 * 2**20, "HelixBoot", "/run/media/me/HelixBoot"),
                                      (32 * 2**20, "VTOYEFI", None)], rm=True, vendor="SanDisk", model="Ultra", serial="S1")
CARD = disk("mmcblk0", None, 16 * GB, [(16 * GB, "CARD", None)], rm=True)


def disks(*found, protected=("/dev/nvme0n1",)):
    with mock.patch.object(gui, "_diskseq", lambda name: "7"):
        return gui.all_disks(lsblk={"blockdevices": list(found)}, protected=set(protected))


class TestDisks(unittest.TestCase):
    def test_only_usb_and_card_disks_that_dont_hold_the_system_are_offered(self):
        with mock.patch.object(app, "all_disks", lambda run=None: disks(NVME, USB_HDD, PLAIN, CARD)):
            offered = app.usb_disks()
        self.assertEqual([d["Number"] for d in offered], ["mmcblk0", "sdb"])
        self.assertEqual([d["Bus"] for d in offered], ["SD", "USB"])
        everything = {d["Number"]: d for d in disks(NVME, USB_HDD, PLAIN)}
        self.assertTrue(everything["nvme0n1"]["System"])
        self.assertEqual(everything["sda"]["Bus"], "SATA")           # an external hard disk on SATA: not offered
        # A USB disk the system runs from is never offered, whatever it looks like
        with mock.patch.object(app, "all_disks", lambda run=None: disks(PLAIN, protected=("/dev/sdb",))):
            self.assertEqual(app.usb_disks(), [])
            with self.assertRaisesRegex(app.RescueError, "holds the running system"):
                app.pick("sdb")

    def test_a_ventoy_stick_is_known_by_ventoys_partition_whatever_it_is_named(self):
        d = disks(VENTOY)[0]
        self.assertEqual((d["IsVentoy"], d["Ventoy"], d["Efi"]), (True, "/dev/sdb1", "/dev/sdb2"))
        self.assertEqual(d["Name"], "SanDisk Ultra")
        self.assertEqual(gui.where_text(d), "HelixBoot")
        plain = disks(PLAIN)[0]
        self.assertEqual((plain["IsVentoy"], plain["Ventoy"], gui.where_text(plain)), (False, None, ""))

    def test_no_answer_about_the_system_disks_means_no_disks(self):
        with mock.patch.object(gui.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="")):
            with self.assertRaisesRegex(app.RescueError, "no disk is offered"):
                gui.system_disks()
        with mock.patch.object(gui.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="/dev/nvme0n1\n")):
            self.assertEqual(gui.system_disks(), {"/dev/nvme0n1"})

    def test_a_stick_swapped_for_another_is_a_different_disk(self):
        first = disks(PLAIN)[0]
        with mock.patch.object(gui, "_diskseq", lambda name: "8"):
            second = gui.all_disks(lsblk={"blockdevices": [PLAIN]}, protected=set())[0]
        self.assertNotEqual(gui.disk_identity(first), gui.disk_identity(second))    # same name, same model
        with self.assertRaisesRegex(app.RescueError, "refusing to write"):
            gui.disk_identity({**first, "Id": ""})
        with mock.patch.object(app, "all_disks", lambda run=None: [second]):
            with self.assertRaisesRegex(app.RescueError, "was replaced"):
                app.recheck_disk(first)


class TestVentoy(unittest.TestCase):
    def test_arguments_for_ventoys_installer(self):
        with mock.patch.object(app, "config", lambda: mock.Mock(stick_label="HelixBoot")):
            self.assertEqual(gui.ventoy_command(Path("v"), "/I", "sdb"), ["-I", "-L", "HelixBoot", "-g", "-s", "/dev/sdb"])
            self.assertEqual(gui.ventoy_command(Path("v"), "/I", "sdb", gpt=False, secure_boot=False),
                             ["-I", "-L", "HelixBoot", "-S", "/dev/sdb"])
            self.assertEqual(gui.ventoy_command(Path("v"), "/U", "mmcblk0", secure_boot=False), ["-u", "-S", "/dev/mmcblk0"])
            for bad in ("sdb1", "../sdb", "sdb; rm -rf /", 2, ""):
                with self.assertRaisesRegex(app.RescueError, "isn't a disk's name"):
                    gui.ventoy_command(Path("v"), "/I", bad)
        with mock.patch.object(app, "config", lambda: mock.Mock(stick_label="Ventoy")):
            self.assertEqual(gui.ventoy_command(Path("v"), "/I", "sdb"), ["-I", "-g", "-s", "/dev/sdb"])

    def run_ventoy(self, code=0, said="Install Ventoy to /dev/sdb successfully finished.\n"):
        calls = []

        def as_root(cmd, feed="", timeout=0):
            calls.append(("root", cmd, feed))
            return code, said
        out = io.StringIO()
        with mock.patch.object(gui, "partitions", lambda dev: [f"{dev}1", f"{dev}2"]), \
                mock.patch.object(gui, "unmount", lambda part: calls.append(("unmount", part))), \
                mock.patch.object(gui, "as_root", as_root), mock.patch.object(gui.subprocess, "run"), \
                redirect_stdout(out):
            gui.run_ventoy(["-I", "-g", "-s", "/dev/sdb"], Path("/cache/ventoy-1.1.17"))
        return calls

    def test_the_disk_is_unmounted_and_ventoys_script_run_as_root_from_its_folder(self):
        calls = self.run_ventoy()
        self.assertEqual(calls[:2], [("unmount", "/dev/sdb1"), ("unmount", "/dev/sdb2")])
        kind, cmd, feed = calls[2]
        self.assertEqual(cmd[:2], ["/bin/sh", "-c"])
        self.assertEqual(cmd[3:], ["helix-boot", "/cache/ventoy-1.1.17", "-I", "-g", "-s", "/dev/sdb"])
        self.assertIn('cd "$1" && shift && exec ./Ventoy2Disk.sh "$@"', cmd[2])      # arguments stay arguments
        self.assertEqual(feed, "y\ny\n")                                             # its two "Continue?"s

    def test_ventoys_own_words_decide_whether_it_worked(self):
        for code, said in ((0, "Continue? (y/n) n\n"), (1, "Install Ventoy to /dev/sdb successfully finished."),
                           (0, "/dev/sdb is already mounted, please umount it first!")):
            with self.assertRaisesRegex(app.RescueError, "didn't finish on /dev/sdb"):
                self.run_ventoy(code, said)

    def test_no_password_no_writing(self):
        with mock.patch.object(gui.shutil, "which", lambda name: "/usr/bin/pkexec"), \
                mock.patch.object(gui.subprocess, "run", return_value=mock.Mock(returncode=126, stdout="", stderr="")):
            with self.assertRaisesRegex(app.RescueError, "password wasn't given"):
                gui.as_root(["/bin/true"])
        with mock.patch.object(gui.shutil, "which", lambda name: None):
            with self.assertRaisesRegex(app.RescueError, "no pkexec"):
                gui.as_root(["/bin/true"])

    def test_ventoy_comes_from_the_cache_or_the_pack(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = mock.Mock(cache=tmp)
        with mock.patch.object(gui.cr, "load_lock", lambda cfg: {"ventoy": {"final": "ventoy-1.1.17"}}):
            with self.assertRaisesRegex(app.RescueError, "isn't downloaded"):
                gui.ventoy_dir(cfg)
            (tmp / "ventoy/ventoy-1.1.17").mkdir(parents=True)
            (tmp / "ventoy/ventoy-1.1.17/Ventoy2Disk.sh").write_text("#!/bin/sh\n")
            self.assertEqual(gui.ventoy_dir(cfg), tmp / "ventoy/ventoy-1.1.17")
        with mock.patch.object(gui.cr, "_ventoy_from_pack", lambda cfg, pack, windows: (pack, windows)):
            self.assertEqual(gui.pack_ventoy_dir(cfg, "pack.zip"), ("pack.zip", False))


class TestFlows(unittest.TestCase):
    """The window's own install and update steps (windows/helix_boot.py), on Linux's parts."""

    def setUp(self):
        self.calls = []
        self.state = {"disks": [PLAIN], "seq": "7"}
        fakes = {
            app: dict(config=lambda: mock.Mock(stick_label="HelixBoot"),
                      fetch=lambda cfg, tools=(): self.calls.append("fetch") or True,
                      sync=lambda cfg, target, init: self.calls.append(("sync", target, init)),
                      unpack=lambda cfg, target, pack, init: self.calls.append(("unpack", target, str(pack))),
                      update_summary=lambda cfg, target, pack=None, **kw: "Copy 1 (1.0 GiB): Clonezilla 3.3",
                      all_disks=lambda run=None: self.now(), ventoy_dir=lambda cfg: Path("/cache/ventoy"),
                      pack_ventoy_dir=lambda cfg, pack: Path("/cache/from-pack"),
                      boot_script=lambda target, disk_no=None, run=None: self.calls.append(("boot script", target, disk_no))),
            gui: dict(mount=lambda part: self.calls.append(("mount", part)) or "/run/media/me/HelixBoot",
                      run_ventoy=self.ventoy),
            app.cr: dict(update_plan=lambda *a, **k: []),
        }
        for module, names in fakes.items():
            for name, fake in names.items():
                p = mock.patch.object(module, name, fake)
                p.start()
                self.addCleanup(p.stop)
        p = mock.patch.object(app, "run_ventoy", self.ventoy)
        p.start()
        self.addCleanup(p.stop)

    def now(self):
        with mock.patch.object(gui, "_diskseq", lambda name: self.state["seq"]):
            return gui.all_disks(lsblk={"blockdevices": self.state["disks"]}, protected={"/dev/nvme0n1"})

    def ventoy(self, args, vdir, progress=lambda pct: None, timeout=0):
        self.calls.append(("ventoy", args, str(vdir)))
        self.state["disks"] = [VENTOY]

    def quiet(self, fn, *a, **kw):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return fn(*a, **kw)

    def test_install_erases_installs_ventoy_mounts_and_fills(self):
        where = self.quiet(app.install, "sdb")
        self.assertEqual(where, "/run/media/me/HelixBoot")
        self.assertEqual(self.calls[:2], ["fetch", ("ventoy", ["-I", "-L", "HelixBoot", "-g", "-s", "/dev/sdb"], "/cache/ventoy")])
        self.assertIn(("mount", "/dev/sdb1"), self.calls)
        done = [c for c in self.calls if c[0] in ("sync", "boot script")]
        self.assertEqual(done, [("sync", "/run/media/me/HelixBoot", True), ("boot script", "/run/media/me/HelixBoot", "sdb")])

    def test_install_from_a_pack_downloads_nothing(self):
        self.quiet(app.install, "sdb", pack=Path("pack.zip"), secure_boot=False, gpt=False)
        self.assertNotIn("fetch", self.calls)
        self.assertEqual(self.calls[0], ("ventoy", ["-I", "-L", "HelixBoot", "-S", "/dev/sdb"], "/cache/from-pack"))
        self.assertIn(("unpack", "/run/media/me/HelixBoot", "pack.zip"), self.calls)

    def test_install_refuses_the_system_disk_and_a_disk_swapped_on_the_way(self):
        self.state["disks"] = [NVME]
        with self.assertRaisesRegex(app.RescueError, "holds the running system"):
            self.quiet(app.install, "nvme0n1")
        self.state["disks"] = [PLAIN]
        picked = self.now()[0]
        self.state["seq"] = "8"                                 # another stick is /dev/sdb now
        with self.assertRaisesRegex(app.RescueError, "was replaced"):
            self.quiet(app.install, "sdb", expected=picked)
        self.assertEqual(self.calls, [])

    def test_update_keeps_the_stick_and_only_upgrades_ventoy_when_asked(self):
        self.state["disks"] = [VENTOY]
        where = self.quiet(app.update, "sdb")
        self.assertEqual(where, "/run/media/me/HelixBoot")
        self.assertEqual([c for c in self.calls if c[0] == "ventoy"], [])
        done = [c for c in self.calls if c[0] in ("sync", "boot script")]
        self.assertEqual(done, [("sync", "/run/media/me/HelixBoot", True), ("boot script", "/run/media/me/HelixBoot", "sdb")])
        self.calls.clear()
        self.quiet(app.update, "sdb", upgrade_ventoy=True)
        self.assertIn(("ventoy", ["-u", "-s", "/dev/sdb"], "/cache/ventoy"), self.calls)
        self.state["disks"] = [PLAIN]
        with self.assertRaisesRegex(app.RescueError, "doesn't have Ventoy"):
            self.quiet(app.update, "sdb")


class TestRepairAndBootScript(unittest.TestCase):
    def repair(self, code, said="fsck.exfat 1.2\n"):
        calls = []
        fakes = dict(
            run=lambda cmd, timeout=60, **kw: "/dev/sdb1\n", mounted_at=lambda part: "/run/media/me/HelixBoot",
            unmount=lambda part: calls.append(("unmount", part)), mount=lambda part: calls.append(("mount", part)) or "/m",
            as_root=lambda cmd, feed="", timeout=0: calls.append(("root", cmd[1:])) or (code, said))
        with mock.patch.multiple(gui, **fakes), mock.patch.object(gui.shutil, "which", lambda n: "/usr/sbin/fsck"), \
                redirect_stdout(io.StringIO()):
            try:
                return gui.repair("/run/media/me/HelixBoot"), calls
            except app.RescueError as e:
                return e, calls

    def test_repair_unmounts_runs_fsck_and_mounts_again(self):
        text, calls = self.repair(0)
        self.assertIn("found nothing wrong", text)
        self.assertEqual(calls, [("unmount", "/dev/sdb1"), ("root", ["-y", "/dev/sdb1"]), ("mount", "/dev/sdb1")])
        self.assertIn("had errors and they were repaired", self.repair(1)[0])
        failed, calls = self.repair(4, "couldn't repair")
        self.assertIn("fsck couldn't repair /dev/sdb1", str(failed))
        self.assertEqual(calls[-1], ("mount", "/dev/sdb1"))             # mounted again whatever happened

    def test_repair_refuses_what_isnt_a_mounted_partition(self):
        with mock.patch.object(gui, "run", lambda cmd, timeout=60, **kw: "/dev/mapper/x[/@home]\n"), \
                mock.patch.object(gui, "mounted_at", lambda part: ""):
            with self.assertRaisesRegex(app.RescueError, "isn't a mounted stick"):
                gui.repair("/home")

    def test_boot_script_mounts_ventoys_partition_and_lets_go_of_it(self):
        calls = []
        cfg = mock.Mock()
        fakes = dict(mount=lambda part: calls.append(("mount", part)) or "/run/media/me/VTOYEFI",
                     unmount=lambda part: calls.append(("unmount", part)))
        with mock.patch.multiple(gui, **fakes), mock.patch.object(app, "config", lambda: cfg), \
                mock.patch.object(app, "all_disks", lambda run=None: disks(VENTOY)), redirect_stdout(io.StringIO()) as out:
            with mock.patch.object(gui.cr, "cmd_splash", lambda cfg, a: calls.append(("splash", a.efi, a.stick)) or 0):
                self.assertTrue(gui.boot_script("/run/media/me/HelixBoot", disk_no="sdb"))
            self.assertEqual(calls, [("mount", "/dev/sdb2"), ("splash", "/run/media/me/VTOYEFI", "/run/media/me/HelixBoot"),
                                     ("unmount", "/dev/sdb2")])
            with mock.patch.object(gui.cr, "cmd_splash", lambda cfg, a: 1), \
                    mock.patch.object(gui.cr, "forget_keys_hook", lambda cfg, mnt: calls.append("forgot")):
                self.assertFalse(gui.boot_script("/run/media/me/HelixBoot", disk_no="sdb"))     # never fatal
            self.assertIn("forgot", calls)
            self.assertIn("no splash", out.getvalue())


class TestFront(unittest.TestCase):
    def test_refuses_to_run_as_root_and_shows_help(self):
        err = io.StringIO()
        with mock.patch.object(gui.os, "geteuid", lambda: 0), redirect_stderr(err):
            self.assertEqual(gui.main([]), 1)
        self.assertIn("normal user", err.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(gui.main(["--help"]), 0)
        self.assertIn("--list", out.getvalue())

    def test_the_window_is_told_this_is_not_windows(self):
        self.assertIs(app.stick_path, gui.stick_path)
        self.assertIs(app.wait_for_ventoy_letter, gui.wait_for_stick)
        self.assertNotIn("Windows", app.SAFE_TO_REMOVE + app.NO_LETTER + app.SYSTEM + gui.repair_question({"Ventoy": "/dev/sdb1"}))


if __name__ == "__main__":
    unittest.main()
