"""Tests for HelixBoot.sh, the one-file Linux installer built by linux/build.sh."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless((ROOT / ".git").exists() and shutil.which("git"), "needs a git checkout")
class TestLinuxInstaller(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="helixboot-sh-"))
        cls.built = cls.tmp / "HelixBoot.sh"
        r = subprocess.run([str(ROOT / "linux/build.sh"), str(cls.built)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(dir=self.tmp))
        self.folder = self.home / "Downloads"        # where you'd keep it: a folder of its own
        self.folder.mkdir()
        self.sh = self.folder / "HelixBoot.sh"
        shutil.copy2(self.built, self.sh)

    def run_it(self, *args, sh=None, stdin=""):
        env = {**os.environ, "HOME": str(self.home), "XDG_DATA_HOME": str(self.home / "data"), "NO_COLOR": "1"}
        env.pop("HELIX_USER_DIR", None)
        return subprocess.run([str(sh or self.sh), *args], capture_output=True, text=True, env=env,
                              input=stdin, timeout=120)

    def test_runs_from_one_file(self):
        version = subprocess.run([str(ROOT / "helix"), "--version"], capture_output=True, text=True).stdout.split()[-1]
        r = self.run_it("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"Helix Boot {version} (HelixBoot.sh)")
        apps = list((self.home / "data/helix-boot/app").iterdir())
        self.assertEqual(len(apps), 1)
        self.assertTrue(apps[0].name.startswith(f"{version}-"))
        for f in ("helix", "install.sh", "refresh.sh", "theme.sh", "scripts/common.sh", "tools.toml", "theme/theme.txt",
                  "theme/presets/midnight/theme.txt", "theme/icon-packs/badges/pack.toml",
                  "pe/launcher/HelixApps.cmd", "pe/launcher/FindStick.ps1", "pe/lazarus/LazarusLauncher.ps1"):
            self.assertTrue((apps[0] / f).is_file(), f)
        self.assertTrue(os.access(apps[0] / "install.sh", os.X_OK))
        self.assertFalse(list(apps[0].rglob("*.py")), "build scripts don't belong in it")
        self.assertTrue((self.folder / "byo/README.md").is_file())   # your folder, next to it

    def test_your_local_toml_beside_it_is_used(self):
        (self.folder / "local.toml").write_text('[overrides.hirens]\nenabled = false\n')
        r = self.run_it("helix", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        hirens = next(line for line in r.stdout.splitlines() if line.startswith("hirens"))
        self.assertTrue(hirens.rstrip().endswith("no"), hirens)

    def test_passes_commands_through(self):
        r = self.run_it("install", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Usage: ./install.sh", r.stdout)
        r = self.run_it("theme", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Usage: ./theme.sh", r.stdout)
        r = self.run_it("bogus")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown command", r.stderr)

    def test_menu(self):
        r = self.run_it(stdin="q\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue("HELIX BOOT" in r.stdout or "██╗" in r.stdout, r.stdout)   # logo, or its plain form
        self.assertEqual(r.stdout.count("RECOVERY") + r.stdout.count("HELIX BOOT"), 1, "the banner, once")
        for line in ("Install on a new USB stick", "Update a Helix Boot stick", "Change a stick's look",
                     "Check for tool updates"):
            self.assertIn(line, r.stdout)

    def test_a_changed_file_is_refused(self):
        bad = self.folder / "changed.sh"
        data = bytearray(self.built.read_bytes())
        data[-100] ^= 0xFF
        bad.write_bytes(bytes(data))
        bad.chmod(0o755)
        r = self.run_it("--version", sh=bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("checksum mismatch", r.stderr)
        self.assertFalse((self.home / "data/helix-boot/app").exists() and
                         any((self.home / "data/helix-boot/app").iterdir()))

    def test_refuses_root(self):
        text = self.built.read_bytes()
        self.assertIn(b'[[ $EUID -ne 0 ]] || fail "run this as your normal user', text)

    def test_build_is_reproducible(self):
        again = self.tmp / "again.sh"
        subprocess.run([str(ROOT / "linux/build.sh"), str(again)], check=True, capture_output=True)
        self.assertEqual(again.read_bytes(), self.built.read_bytes())


if __name__ == "__main__":
    unittest.main()
