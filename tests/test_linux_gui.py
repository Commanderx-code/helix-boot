"""Tests for linux/helix_gui.py: the Linux parts under the window, with lsblk, udisks, pkexec and
Ventoy faked, so they run anywhere and touch no disk."""
import hashlib
import importlib.util
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
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

    WANT = "ab" * 32

    def run_ventoy(self, code=0, said="Install Ventoy to /dev/sdb successfully finished.\n", verified=True):
        calls = []

        def as_root(cmd, feed="", timeout=0):
            calls.append(("root", cmd, feed))
            return code, said
        archive = Path("/cache/ventoy/ventoy-1.1.17-linux.tar.gz")
        out = io.StringIO()
        with mock.patch.object(gui, "partitions", lambda dev: [f"{dev}1", f"{dev}2"]), \
                mock.patch.object(gui, "unmount", lambda part: calls.append(("unmount", part))), \
                mock.patch.object(gui, "as_root", as_root), mock.patch.object(gui.subprocess, "run"), \
                mock.patch.dict(gui.VERIFIED, {str(archive): self.WANT} if verified else {}, clear=True), \
                redirect_stdout(out):
            gui.run_ventoy(["-I", "-g", "-s", "/dev/sdb"], archive)
        return calls

    def test_the_disk_is_unmounted_and_root_is_given_the_archive_and_its_checksum(self):
        calls = self.run_ventoy()
        self.assertEqual(calls[:2], [("unmount", "/dev/sdb1"), ("unmount", "/dev/sdb2")])
        kind, cmd, feed = calls[2]
        self.assertEqual(cmd[:2], ["/bin/sh", "-c"])
        self.assertEqual(cmd[2], gui.RUN_VENTOY)                                     # a fixed script, nothing built in
        self.assertEqual(cmd[3:], ["helix-boot", "/cache/ventoy/ventoy-1.1.17-linux.tar.gz", self.WANT,
                                   "-I", "-g", "-s", "/dev/sdb"])                    # arguments stay arguments
        self.assertEqual(feed, "y\ny\n")                                             # Ventoy's two "Continue?"s

    def test_an_archive_this_run_didnt_verify_is_never_run_as_root(self):
        with self.assertRaisesRegex(app.RescueError, "refusing to run it as root"):
            self.run_ventoy(verified=False)

    def test_ventoys_own_words_decide_whether_it_worked(self):
        for code, said in ((0, "Continue? (y/n) n\n"), (1, "Install Ventoy to /dev/sdb successfully finished."),
                           (0, "/dev/sdb is already mounted, please umount it first!")):
            with self.assertRaisesRegex(app.RescueError, "didn't finish on /dev/sdb"):
                self.run_ventoy(code, said)

    def root_script(self, tmp, archive, want, *args):
        """Root's script, run as you: its working folder in a temporary folder and not /run."""
        script = gui.RUN_VENTOY.replace("/run/helix-boot.", f"{tmp}/work/helix-boot.")
        (tmp / "work").mkdir(exist_ok=True)
        return subprocess.run(["/bin/sh", "-c", script, "helix-boot", str(archive), want, *args],
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def test_root_runs_its_own_checked_copy_and_nothing_from_your_folders(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "ventoy-9.9"
        src.mkdir()
        (src / "Ventoy2Disk.sh").write_text('#!/bin/sh\necho "ran in $PWD with $*"\necho "successfully finished"\n')
        (src / "Ventoy2Disk.sh").chmod(0o755)
        archive = tmp / "ventoy-9.9-linux.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src, arcname="ventoy-9.9")
        want = hashlib.sha256(archive.read_bytes()).hexdigest()
        # What is unpacked beside it is yours to change: it is not what runs
        (src / "Ventoy2Disk.sh").write_text("#!/bin/sh\necho CHANGED\n")
        r = self.root_script(tmp, archive, want, "-I", "-g", "/dev/sdz")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("with -I -g /dev/sdz", r.stdout)
        self.assertIn(f"ran in {tmp}/work/helix-boot.", r.stdout)                    # from root's own copy
        self.assertNotIn("CHANGED", r.stdout)
        self.assertEqual(list((tmp / "work").iterdir()), [])                         # and that copy is gone again

        # An archive that isn't the verified one is refused before anything in it is run
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src, arcname="ventoy-9.9")
        r = self.root_script(tmp, archive, want, "-I", "/dev/sdz")
        self.assertEqual(r.returncode, 97)
        self.assertIn("not the one that was verified", r.stderr)
        self.assertNotIn("CHANGED", r.stdout)
        self.assertEqual(list((tmp / "work").iterdir()), [])

    def test_no_password_no_writing_and_roots_tools_are_not_found_on_your_path(self):
        with mock.patch.object(gui, "root_tool", lambda name: f"/usr/bin/{name}"), \
                mock.patch.object(gui.subprocess, "run", return_value=mock.Mock(returncode=126, stdout="", stderr="")):
            with self.assertRaisesRegex(app.RescueError, "password wasn't given"):
                gui.as_root(["/bin/true"])
        with mock.patch.object(gui, "ROOT_TOOLS", ("/nonexistent",)), \
                mock.patch.object(gui.subprocess, "run", side_effect=AssertionError("nothing may be run")):
            with self.assertRaisesRegex(app.RescueError, "no pkexec"):
                gui.as_root(["/bin/true"])
        mine = Path(tempfile.mkdtemp())
        (mine / "sh").write_text("#!/bin/sh\n")
        (mine / "sh").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{mine}:{os.environ['PATH']}"}):
            self.assertNotEqual(Path(gui.root_tool("sh")).parent, mine)
            self.assertTrue(gui.root_tool("sh").startswith(gui.ROOT_TOOLS))

    def test_ventoys_archive_must_be_the_file_ventoy_published(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = mock.Mock(cache=tmp)
        (tmp / "ventoy").mkdir()
        name = "ventoy-1.1.17-linux.tar.gz"
        archive = tmp / "ventoy" / name
        good = hashlib.sha256(b"ventoy as published").hexdigest()
        # What the cache says about itself counts for nothing: this lock vouches for the altered file
        lock = {"ventoy": {"source_file": name, "sha256_download": hashlib.sha256(b"altered").hexdigest(),
                           "verified_by": "sha256 from sha256.txt"}}
        with mock.patch.object(gui.cr, "load_lock", lambda cfg: lock), mock.patch.dict(gui.VERIFIED, clear=True), \
                mock.patch.dict(gui.VENTOY_SHA256, {name: good}, clear=True), \
                mock.patch.object(gui.cr, "http_get", side_effect=AssertionError("a listed archive needs no asking")):
            with self.assertRaisesRegex(app.RescueError, "isn't downloaded"):
                gui.ventoy_dir(cfg)
            archive.write_bytes(b"altered")
            with self.assertRaisesRegex(app.RescueError, "not the file Ventoy published"):
                gui.ventoy_dir(cfg)
            self.assertEqual(gui.VERIFIED, {})
            archive.write_bytes(b"ventoy as published")
            self.assertEqual(gui.ventoy_dir(cfg), archive)
            self.assertEqual(gui.VERIFIED, {str(archive): good})

    def test_a_ventoy_newer_than_the_program_knows_is_checked_with_ventoys_release(self):
        name = "ventoy-1.2.0-linux.tar.gz"
        good = hashlib.sha256(b"new ventoy").hexdigest()
        asked = []

        def release(url, *a, **k):
            asked.append(url)
            return f"{'0' * 64}  ventoy-1.2.0-windows.zip\n{good}  {name}\n".encode()
        with mock.patch.dict(gui.VENTOY_SHA256, {}, clear=True):
            with mock.patch.object(gui.cr, "http_get", release):
                self.assertEqual(gui.ventoy_sha256(name), good)
            self.assertEqual(asked, ["https://github.com/ventoy/Ventoy/releases/download/v1.2.0/sha256.txt"])
            with mock.patch.object(gui.cr, "http_get", side_effect=gui.cr.RescueError("couldn't reach github.com")):
                with self.assertRaisesRegex(app.RescueError, "newer than this program knows.*couldn't reach"):
                    gui.ventoy_sha256(name)                                  # offline: not run, not guessed
            with mock.patch.object(gui.cr, "http_get", lambda url, *a, **k: b"nothing about that file\n"):
                with self.assertRaisesRegex(app.RescueError, "lists no checksum"):
                    gui.ventoy_sha256(name)
            for odd in ("ventoy.tar.gz", "ventoy-1.2.0-linux.tar.gz.sh", "../ventoy-1.2.0-linux.tar.gz", "evil-1.0-linux.tar.gz"):
                with mock.patch.object(gui.cr, "http_get", side_effect=AssertionError("not asked")):
                    with self.assertRaisesRegex(app.RescueError, "isn't named as Ventoy's"):
                        gui.ventoy_sha256(odd)

    def test_a_packs_ventoy_is_held_to_the_same_checksum(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = mock.Mock(cache=tmp)
        name = "ventoy-1.1.17-linux.tar.gz"
        for content, ok in ((b"ventoy as published", True), (b"something else in the pack", False)):
            pack = tmp / "pack.zip"
            with zipfile.ZipFile(pack, "w") as z:
                z.writestr("installer/" + name, content)
            meta = {"ventoy": {"file": "installer/" + name, "version": "1.1.17"}}
            with mock.patch.object(gui.cr, "_open_pack", lambda p: zipfile.ZipFile(p)), \
                    mock.patch.object(gui.cr, "_read_pack", lambda zf: meta), mock.patch.dict(gui.VERIFIED, clear=True), \
                    mock.patch.dict(gui.VENTOY_SHA256, {name: hashlib.sha256(b"ventoy as published").hexdigest()}, clear=True):
                if ok:
                    self.assertEqual(gui.pack_ventoy_dir(cfg, pack).name, name)
                    self.assertEqual(len(gui.VERIFIED), 1)
                else:
                    with self.assertRaisesRegex(app.RescueError, "not the file Ventoy published"):
                        gui.pack_ventoy_dir(cfg, pack)
                    self.assertEqual(gui.VERIFIED, {})

    def test_the_listed_checksums_are_well_formed(self):
        self.assertTrue(gui.VENTOY_SHA256)
        for name, sha in gui.VENTOY_SHA256.items():
            self.assertRegex(name, r"^ventoy-\d+(\.\d+)+-linux\.tar\.gz$")
            self.assertRegex(sha, r"^[0-9a-f]{64}$")


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
        with mock.patch.multiple(gui, **fakes), mock.patch.object(gui, "root_tool", lambda n: f"/usr/sbin/{n}"), \
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
