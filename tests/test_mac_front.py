"""mac/helix-mac, with diskutil faked: which disks count as sticks, and the order an update goes in."""
import importlib.machinery
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("helix_mac", str(ROOT / "mac/helix-mac"))
spec = importlib.util.spec_from_loader("helix_mac", loader)
mac = importlib.util.module_from_spec(spec)
loader.exec_module(mac)

GB = 1000**3


class Disks:
    """A stand-in for diskutil: one Mac disk, one stick (renamed HelixBoot), one plain USB drive."""

    def __init__(self, stick_dir: Path, efi_dir: Path):
        self.calls, self.mounted = [], {"disk4s1": str(stick_dir)}
        self.dirs = {"disk4s1": str(stick_dir), "disk4s2": str(efi_dir)}
        self.listing = {"AllDisksAndPartitions": [
            {"DeviceIdentifier": "disk0", "Size": 500 * GB, "Partitions": [
                {"DeviceIdentifier": "disk0s1", "VolumeName": "VTOYEFI", "Size": 32 << 20},     # a decoy inside the Mac
                {"DeviceIdentifier": "disk0s2", "VolumeName": "Macintosh HD", "Size": 499 * GB}]},
            {"DeviceIdentifier": "disk4", "Size": 62 * GB, "Partitions": [
                {"DeviceIdentifier": "disk4s1", "VolumeName": "HelixBoot", "Size": 61 * GB},
                {"DeviceIdentifier": "disk4s2", "VolumeName": "VTOYEFI", "Size": 32 << 20}]},
            {"DeviceIdentifier": "disk5", "Size": 16 * GB, "Partitions": [
                {"DeviceIdentifier": "disk5s1", "VolumeName": "PHOTOS", "Size": 16 * GB}]}]}
        self.info = {"disk0": {"Internal": True, "TotalSize": 500 * GB, "MediaName": "APPLE SSD"},
                     "disk4": {"Internal": False, "TotalSize": 62 * GB, "MediaName": "SanDisk 3.2Gen1", "BusProtocol": "USB"},
                     "disk5": {"Internal": False, "TotalSize": 16 * GB, "MediaName": "Card", "BusProtocol": "USB"}}

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("list", "-plist"):
            if len(args) == 3:
                return {"AllDisksAndPartitions": [d for d in self.listing["AllDisksAndPartitions"]
                                                  if d["DeviceIdentifier"] == args[2]]}
            return self.listing
        if args[:2] == ("info", "-plist"):
            what = args[2]
            if what in self.info:
                return self.info[what]
            part = next((p for p, d in self.dirs.items() if what in (p, d)), None)
            return {"DeviceIdentifier": part, "MountPoint": self.mounted.get(part)} if part else {}
        if args[0] == "mount":
            self.mounted[args[1]] = self.dirs[args[1]]
        elif args[0] == "unmount":
            self.mounted.pop(args[1], None)
        elif args[0] == "unmountDisk":
            self.mounted = {p: d for p, d in self.mounted.items() if not p.startswith(args[-1])}
        elif args[0] == "eraseVolume":
            self.mounted[args[3]] = self.dirs[args[3]]
        return {}


class TestMacFront(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="helix-mac-test-"))
        self.stick, self.efi = self.tmp / "HelixBoot", self.tmp / "VTOYEFI"
        self.stick.mkdir()
        self.efi.mkdir()
        self.run = Disks(self.stick, self.efi)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def args(self, **kw):
        base = dict(disk=None, pack=None, no_fetch=False, verify=False, prune_unknown=False, yes=False, eject=False)
        return mac.ns(**{**base, **kw})

    def test_only_an_external_disk_with_ventoys_partition_is_a_stick(self):
        found = mac.sticks(self.run)
        self.assertEqual([s["disk"] for s in found], ["disk4"])            # not the Mac's own disk, nor a plain drive
        self.assertEqual((found[0]["data"], found[0]["efi"], found[0]["label"]), ("disk4s1", "disk4s2", "HelixBoot"))
        self.assertEqual(mac.pick(None, self.run)["disk"], "disk4")
        self.assertEqual(mac.pick("/dev/disk4", self.run)["disk"], "disk4")
        for disk in ("disk0", "disk5", "disk9"):                           # named, but not a stick: refused
            with self.assertRaisesRegex(mac.cr.RescueError, "isn't a Helix Boot / Ventoy stick"):
                mac.pick(disk, self.run)

    def test_an_mbr_sticks_ventoy_partition_has_no_name_on_a_mac(self):
        # macOS doesn't read the name of an EFI system partition on an MBR disk: it is known by
        # its type and Ventoy's size instead. Another size, or another type, isn't Ventoy's.
        part = self.run.listing["AllDisksAndPartitions"][1]["Partitions"][1]
        part.pop("VolumeName")
        part.update(Content="0xEF", Size=65536 * 512)
        self.assertEqual(mac.pick(None, self.run)["efi"], "disk4s2")
        for change in ({"Size": 200 << 20}, {"Content": "Windows_FAT_32"}):
            part.update(Content="0xEF", Size=65536 * 512)
            part.update(change)
            with self.assertRaisesRegex(mac.cr.RescueError, "no Helix Boot / Ventoy stick found"):
                mac.pick(None, self.run)

    def test_none_or_several_sticks(self):
        self.run.listing["AllDisksAndPartitions"][2]["Partitions"].append(
            {"DeviceIdentifier": "disk5s2", "VolumeName": "VTOYEFI", "Size": 32 << 20})
        with self.assertRaisesRegex(mac.cr.RescueError, "more than one stick"):
            mac.pick(None, self.run)
        self.run.listing["AllDisksAndPartitions"] = self.run.listing["AllDisksAndPartitions"][:1]
        with self.assertRaisesRegex(mac.cr.RescueError, "no Helix Boot / Ventoy stick found"):
            mac.pick(None, self.run)

    def update(self, a, ask=lambda q: "y"):
        steps = []
        fakes = dict(
            cmd_fetch=lambda cfg, n: steps.append("fetch") or 0,
            update_plan=lambda cfg, target, pack, **kw: steps.append(("plan", target, pack, kw["verify"])) or [("copy", "X", 1)],
            cmd_sync=lambda cfg, n: steps.append(("sync", n.target, n.init, n.dry_run)) or 0,
            cmd_unpack=lambda cfg, n: steps.append(("unpack", n.pack, n.target)) or 0,
            cmd_splash=lambda cfg, n: steps.append(("splash", n.efi, n.stick)) or 0,
            forget_keys_hook=lambda cfg, mnt: steps.append("forget"),
        )
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            with mock.patch.multiple(mac.cr, **fakes), mock.patch.object(mac, "config", lambda: mock.Mock()):
                try:
                    rc = mac.update(a, run=self.run, ask=ask)
                except mac.cr.RescueError as e:
                    rc = str(e)
        return rc, steps, out.getvalue()

    def test_update_fetches_shows_the_plan_asks_then_writes(self):
        rc, steps, out = self.update(self.args())
        self.assertEqual(rc, 0, out)
        self.assertEqual(steps, ["fetch", ("plan", str(self.stick), None, False),
                                 ("sync", str(self.stick), True, False), ("splash", str(self.efi), str(self.stick))])
        self.assertIn("This update will:", out)
        self.assertTrue((self.stick / ".metadata_never_index").exists())       # Spotlight is asked to stay off it
        self.assertNotIn("disk4s2", self.run.mounted)                          # Ventoy's partition is unmounted again
        self.assertNotIn(("eject", "disk4"), self.run.calls)

    def test_saying_no_changes_nothing(self):
        rc, steps, out = self.update(self.args(), ask=lambda q: "n")
        self.assertIn("nothing on the stick was changed", rc)
        self.assertEqual([s if isinstance(s, str) else s[0] for s in steps], ["fetch", "plan"])
        self.assertFalse((self.stick / ".metadata_never_index").exists())

    def test_from_a_pack_downloads_nothing_and_can_eject(self):
        rc, steps, out = self.update(self.args(pack="pack.zip", yes=True, eject=True), ask=lambda q: self.fail("asked"))
        self.assertEqual(rc, 0, out)
        self.assertEqual([s if isinstance(s, str) else s[0] for s in steps], ["plan", "unpack", "splash"])
        self.assertEqual(steps[1], ("unpack", "pack.zip", str(self.stick)))
        self.assertIn(("eject", "disk4"), self.run.calls)

    def test_a_stick_swapped_after_the_question_is_not_written(self):
        def swap(question):
            self.run.info["disk4"] = {"Internal": False, "TotalSize": 128 * GB, "MediaName": "Another"}
            return "y"
        rc, steps, out = self.update(self.args(), ask=swap)
        self.assertIn("unplugged or replaced", rc)
        self.assertNotIn("sync", [s if isinstance(s, str) else s[0] for s in steps])

    def test_a_boot_script_that_cant_be_changed_isnt_fatal(self):
        with mock.patch.object(mac.cr, "cmd_splash", side_effect=mac.cr.RescueError("not Ventoy's boot partition")), \
                mock.patch.object(mac.cr, "forget_keys_hook") as forget, redirect_stderr(io.StringIO()) as err:
            mac.boot_script(mock.Mock(), mac.pick(None, self.run), self.stick, self.run)
        forget.assert_called_once()
        self.assertIn("stay Ventoy's Language and Help", err.getvalue())
        self.assertNotIn("disk4s2", self.run.mounted)

    def test_ventoys_partition_is_mounted_directly_when_diskutil_wont(self):
        # On an MBR stick Ventoy's partition is an EFI system partition, which diskutil won't mount
        real, rooted, seen = self.run.__call__, [], []

        def run(*args):
            if args == ("mount", "disk4s2"):
                self.run.calls.append(args)
                raise mac.cr.RescueError("Volume on disk4s2 failed to mount")
            return real(*args)
        with mock.patch.object(mac.cr, "cmd_splash", lambda cfg, n: seen.append(n.efi) or 0), redirect_stderr(io.StringIO()):
            mac.boot_script(mock.Mock(), mac.pick(None, self.run), self.stick, run, lambda *c: rooted.append(c))
        self.assertEqual([c[0] for c in rooted], ["mount_msdos", "umount"])
        self.assertEqual(rooted[0][-2], "/dev/disk4s2")
        self.assertEqual(rooted[0][-1], seen[0])                      # the script is changed where it was mounted
        self.assertEqual(rooted[1][1], seen[0])
        self.assertFalse(Path(seen[0]).exists())                      # and the mount point is tidied away

    # ── install (experimental) ──
    def install(self, ask=lambda q: "disk4", **kw):
        base = dict(disk="disk4", pack=None, no_fetch=True, erase=None, eject=False, allow_disk_image=False)
        steps, root = [], []
        layout = {"head": b"H" * 2048 * 512, "efi": b"E" * 4096, "efi_start": 120_000_000, "data_start": 2048,
                  "data_sectors": 1}
        vdir = self.tmp / "cache/ventoy/ventoy-1.1.17"
        (vdir / "boot").mkdir(parents=True, exist_ok=True)
        (vdir / "boot/boot.img").write_bytes(b"x")
        fakes = dict(
            load_lock=lambda cfg: {"ventoy": {"final": "ventoy-1.1.17"}},
            ventoy_layout=lambda v, sectors: steps.append(("layout", v.name, sectors)) or layout,
            cmd_sync=lambda cfg, n: steps.append(("sync", n.target, n.init, n.verify)) or 0,
            cmd_splash=lambda cfg, n: steps.append(("splash", n.efi, n.stick)) or 0,
        )
        cfg = mock.Mock(cache=self.tmp / "cache", stick_label="HelixBoot")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out), mock.patch.multiple(mac.cr, **fakes), \
                mock.patch.object(mac, "config", lambda: cfg), mock.patch.object(mac.time, "sleep"):
            try:
                rc = mac.install(mac.ns(**{**base, **kw}), run=self.run, ask=ask, root=lambda *c: root.append(c))
            except mac.cr.RescueError as e:
                rc = str(e)
        return rc, steps, root, out.getvalue()

    def test_install_only_erases_a_usb_disk_that_isnt_the_macs(self):
        self.run.info["disk6"] = {"Internal": False, "TotalSize": 2000 * GB, "BusProtocol": "SATA"}
        self.run.info["disk7"] = {"Internal": False, "TotalSize": 1 * GB, "BusProtocol": "Disk Image"}
        for disk, why in (("disk0", "inside this Mac"), ("disk4s1", "whole disk"), ("disk6", "isn't a USB or SD disk"),
                          ("disk7", "isn't a USB or SD disk"), ("../disk4", "whole disk")):
            rc, steps, root, out = self.install(disk=disk)
            self.assertIn(why, rc, disk)
            self.assertEqual((steps, root), ([], []), disk)                 # nothing fetched into place, nothing written
        self.run.mounted["disk4s1"] = "/"                                   # as if the Mac were running from it
        rc, steps, root, out = self.install()
        self.assertIn("running system", rc)
        self.assertEqual(root, [])

    def test_install_needs_the_disks_name_typed(self):
        rc, steps, root, out = self.install(ask=lambda q: "disk5")
        self.assertIn("didn't match", rc)
        self.assertEqual(root, [])
        self.assertIn("ERASE", out)
        self.assertNotIn(("eraseVolume", "ExFAT", "HelixBoot", "disk4s1"), self.run.calls)

    def test_install_writes_ventoy_formats_then_fills(self):
        rc, steps, root, out = self.install(erase="disk4", ask=lambda q: self.fail("asked"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(steps[0], ("layout", "ventoy-1.1.17", 62 * GB // 512))
        self.assertEqual([c[0] for c in root], ["dd", "dd", "sync", "dd", "sync"])
        self.assertEqual(root[0][2:], ("of=/dev/rdisk4", "bs=1m"))                               # the first MiB
        self.assertEqual(root[1][2:], ("of=/dev/rdisk4", "bs=4096", f"seek={120_000_000 // 8}"))   # VTOYEFI, at its sector
        self.assertEqual(root[3][2:], ("of=/dev/rdisk4", "bs=512", "count=1"))                   # the table again
        calls = self.run.calls
        erase = calls.index(("eraseVolume", "ExFAT", "HelixBoot", "disk4s1"))
        self.assertLess(calls.index(("unmountDisk", "force", "disk4")), erase)
        self.assertEqual(steps[1:], [("sync", str(self.stick), True, True), ("splash", str(self.efi), str(self.stick))])
        self.assertEqual(list(Path(tempfile.gettempdir()).glob("helix-install-*")), [])          # its work files are gone

    def test_install_can_test_the_stick_first_and_leaves_a_bad_one_empty(self):
        good = {"asked": GB, "written": GB, "bad": [], "pieces": 1, "error": None, "seconds": 5}
        for found, fails in ((good, False), ({**good, "bad": [0]}, True)):
            tested = []
            with mock.patch.object(mac.cr, "test_stick", lambda mnt, f=found: tested.append(str(mnt)) or f):
                rc, steps, root, out = self.install(erase="disk4", test=True)
            self.assertEqual(tested, [str(self.stick)])
            self.assertEqual(("sync", str(self.stick), True, True) in steps, not fails)
            if fails:
                self.assertIn("failed the test: it is left empty", rc)
                self.assertIn("read back wrong", out)
            else:
                self.assertEqual(rc, 0, out)
                self.assertIn("read back without a fault", out)

    def test_a_stick_that_stays_busy_is_left_for_finder_to_eject(self):
        tried = []

        def run(*cmd):
            tried.append(cmd)
            if len(tried) < 3:
                raise mac.cr.RescueError("diskutil eject disk4: Volume failed to eject: Resource busy")
        out = io.StringIO()
        with mock.patch.object(mac.time, "sleep"), redirect_stdout(out), redirect_stderr(out):
            self.assertTrue(mac.eject("disk4", run))
            self.assertEqual(tried, [("eject", "disk4")] * 3)
            self.assertFalse(mac.eject("disk4", lambda *c: (_ for _ in ()).throw(mac.cr.RescueError("Resource busy"))))
        self.assertIn("eject it in Finder before unplugging", out.getvalue())

    def test_a_busy_disk_is_tried_again(self):
        tried = []

        def root(*cmd):
            tried.append(cmd[2])
            if len(tried) < 3:
                raise mac.cr.RescueError("dd failed: dd: /dev/rdisk4: Resource busy")
        with mock.patch.object(mac.time, "sleep"):
            mac.write_disk("disk4", Path("head.bin"), "bs=1m", run=self.run, root=root)
            self.assertEqual(tried, ["of=/dev/rdisk4"] * 3)
            self.assertEqual(self.run.calls.count(("unmountDisk", "force", "disk4")), 3)      # let go of each time
            tried.clear()
            with self.assertRaisesRegex(mac.cr.RescueError, "stayed busy"):
                mac.write_disk("disk4", Path("head.bin"), run=self.run,
                               root=lambda *c: tried.append(c[2]) or (_ for _ in ()).throw(
                                   mac.cr.RescueError("dd: Resource busy")))
            self.assertEqual(tried[-2:], ["of=/dev/disk4"] * 2)                                # the buffered device last
            with self.assertRaisesRegex(mac.cr.RescueError, "Permission denied"):             # anything else: at once
                mac.write_disk("disk4", Path("head.bin"), run=self.run,
                               root=lambda *c: (_ for _ in ()).throw(mac.cr.RescueError("dd: Permission denied")))

    def test_install_stops_if_the_disk_changes_after_the_question(self):
        def swap(question):
            self.run.info["disk4"] = {"Internal": False, "TotalSize": 128 * GB, "MediaName": "Another", "BusProtocol": "USB"}
            return "disk4"
        rc, steps, root, out = self.install(ask=swap)
        self.assertIn("unplugged or replaced", rc)
        self.assertEqual(root, [])

    def test_partitions_are_waited_for_after_the_table_is_written(self):
        calls = []

        def run(*args):
            calls.append(args)
            if args[0] == "list":
                return {"AllDisksAndPartitions": [{"Partitions": [{"DeviceIdentifier": "disk9s1"},
                                                                  {"DeviceIdentifier": "disk9s2"}]}]}
            if sum(1 for c in calls if c[0] == "info") < 2:
                raise mac.cr.RescueError("Could not find disk: disk9s1")
            return {}
        with mock.patch.object(mac.time, "sleep"):
            mac.partitions_seen("disk9", "disk9s1", "disk9s2", run=run)
            with self.assertRaises(mac.cr.RescueError) as e:
                mac.partitions_seen("disk9", "disk9s3", run=run, tries=3)
        self.assertIn("doesn't see the new partitions", str(e.exception))

    def test_the_one_file_program_makes_your_byo_folder_for_engine_commands_too(self):
        seen = {}
        with mock.patch.object(mac, "FROZEN", True), mock.patch.object(mac, "user_dir", lambda: self.tmp), \
                mock.patch.dict(mac.os.environ), \
                mock.patch.object(mac.cr, "main", lambda argv: seen.update(dir=mac.os.environ["HELIX_USER_DIR"]) or 0):
            self.assertEqual(mac.engine(["--version"]), 0)
        self.assertEqual(seen["dir"], str(self.tmp))
        self.assertTrue((self.tmp / "byo").is_dir())

    def test_every_module_the_engine_imports_is_named_for_the_one_file_build(self):
        # PyInstaller can't see inside helix (it's a data file), so helix-mac imports them for it
        import ast

        def imported(path):
            mods = set()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    mods |= {a.name for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods.add(node.module)
            return mods - {"__future__"}
        only_elsewhere = {"PIL", "ctypes", "msvcrt", "winreg"}       # optional pictures; Windows' own
        missing = imported(ROOT / "helix") - imported(ROOT / "mac/helix-mac") - only_elsewhere
        self.assertEqual(sorted(missing), [], "add these imports to mac/helix-mac")


if __name__ == "__main__":
    unittest.main()
