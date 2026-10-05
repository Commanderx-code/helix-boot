"""Disk discovery tests use synthetic sysfs and command output; no block devices are written."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
UUID = "11111111-2222-3333-4444-555555555555"


class TestSystemDisks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="helix-disk-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, number in (("nvme0n1p2", "259:2"), ("sdb1", "8:17")):
            member = self.root / "sysfs" / UUID / "devices" / name
            member.mkdir(parents=True)
            (member / "dev").write_text(number + "\n")
        self.common = self.root / "common.sh"
        self.common.write_text((ROOT / "scripts/common.sh").read_text().replace(
            "/sys/fs/btrfs/", str(self.root / "sysfs") + "/"))
        self.mocks = r'''
findmnt() {
  [[ ${FAIL:-} != findmnt ]] || return 1
  if [[ ${@: -1} == '/swap disk/swapfile' ]]; then
    printf '/dev/sdc1 ext4 -\n'
  else
    printf '/dev/nvme0n1p2[/@] btrfs %s\n' "$UUID"
  fi
}
swapon() {
  [[ ${FAIL:-} != swapon ]] || return 1
  if [[ ${SWAP_FILE:-} == 1 ]]; then printf '/swap disk/swapfile\n'; fi
}
lsblk() {
  case ${@: -1} in
    /dev/block/259:2) printf '/dev/nvme0n1p2 part\n/dev/nvme0n1 disk\n';;
    /dev/block/8:17)
      [[ ${FAIL:-} != lsblk ]] || return 1
      printf '/dev/sdb1 part\n/dev/sdb disk\n';;
    /dev/sdc1) printf '/dev/sdc1 part\n/dev/sdc disk\n';;
    *) return 1;;
  esac
}
disk_identity() { echo same-device; }
usb_disks() { printf '/dev/sdb\t16G\tSystem member\n/dev/sdd\t16G\tRescue\n'; }
'''

    def run_shell(self, command, **env):
        return subprocess.run(["bash", "-c", 'source "$1"\n' + self.mocks + command,
                               "test", str(self.common)],
                              env=dict(os.environ, UUID=UUID, **env),
                              capture_output=True, text=True, timeout=10)

    def test_all_btrfs_members_are_protected(self):
        result = self.run_shell("system_disks")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["/dev/nvme0n1", "/dev/sdb"])
        refused = self.run_shell("check_disk_identity /dev/sdb same-device; echo WROTE")
        self.assertNotEqual(refused.returncode, 0)
        self.assertNotIn("WROTE", refused.stdout)
        self.assertIn("holds the running system", refused.stderr)
        allowed = self.run_shell("check_disk_identity /dev/sdd same-device; echo ALLOWED")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertIn("ALLOWED", allowed.stdout)

    def test_swap_file_protects_its_backing_disk(self):
        result = self.run_shell("system_disks", SWAP_FILE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/dev/sdc", result.stdout.splitlines())

    def test_failed_discovery_never_returns_partial_list_or_allows_write(self):
        for failure in ("findmnt", "swapon", "lsblk"):
            with self.subTest(failure=failure):
                result = self.run_shell("system_disks", FAIL=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                result = self.run_shell("check_disk_identity /dev/sdd same-device; echo WROTE", FAIL=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("WROTE", result.stdout)
                self.assertIn("cannot determine the system disks", result.stderr)

    def test_missing_btrfs_member_information_stops_discovery(self):
        (self.root / "sysfs" / UUID / "devices/sdb1/dev").unlink()
        result = self.run_shell("system_disks")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_initial_install_refuses_failed_discovery(self):
        script = (ROOT / "install.sh").read_text()
        selection = script[script.index("protected_list=$(system_disks)"):script.index('if [[ -z $dev ]]; then')]
        result = self.run_shell(selection + '\necho CONTINUED', FAIL="findmnt")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("CONTINUED", result.stdout)
        self.assertIn("refusing to install", result.stderr)


if __name__ == "__main__":
    unittest.main()
