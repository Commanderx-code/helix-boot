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
            Config=lambda repo=None: mock.Mock(),
        )
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            with mock.patch.multiple(mac.cr, **fakes):
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


if __name__ == "__main__":
    unittest.main()
