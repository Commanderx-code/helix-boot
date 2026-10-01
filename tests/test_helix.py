"""End-to-end tests for helix against a local fake GitHub / SourceForge / web server.

Run with:  python3 -m unittest discover -s tests -v
"""
import functools
import hashlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import sys
import unittest
import unittest.mock
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(tempfile.mkdtemp(prefix="helix-web-"))


class Quiet(http.server.SimpleHTTPRequestHandler):
    fail = {}  # URL path -> how many more times to answer 500

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.fail.get(self.path, 0) > 0:
            self.fail[self.path] -= 1
            self.send_error(500)
            return
        super().do_GET()


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(WEB)))
BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"
threading.Thread(target=SERVER.serve_forever, daemon=True).start()

os.environ["HELIX_GITHUB_API"] = f"{BASE}/gh"
os.environ["HELIX_SF_RSS"] = BASE + "/sf/{project}/rss{path}/feed.xml"
os.environ["HELIX_SF_DL"] = BASE + "/dl/{project}{path}"
os.environ["NO_COLOR"] = "1"
os.environ.pop("GITHUB_TOKEN", None)

loader = importlib.machinery.SourceFileLoader("helix", str(ROOT / "helix"))
spec = importlib.util.spec_from_loader("helix", loader)
cr = importlib.util.module_from_spec(spec)
loader.exec_module(cr)
cr.RETRY_DELAYS = (0, 0, 0)


def sha(b: bytes, algo="sha256") -> str:
    return hashlib.new(algo, b).hexdigest()


def put(rel: str, data: bytes | str) -> None:
    p = WEB / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode() if isinstance(data, str) else data)


def gh_release(repo: str, tag: str, assets: dict[str, bytes], digests=True) -> None:
    out = []
    for name, data in assets.items():
        put(f"files/{repo}/{tag}/{name}", data)
        a = {"name": name, "size": len(data),
             "browser_download_url": f"{BASE}/files/{repo}/{tag}/{name}"}
        if digests:
            a["digest"] = "sha256:" + sha(data)
        out.append(a)
    put(f"gh/repos/{repo}/releases/latest", json.dumps({"tag_name": tag, "assets": out}))


def sf_feed(project: str, path: str, files: list[tuple[str, bytes, str]]) -> None:
    items = []
    for rel, data, date in files:
        put(f"dl/{project}{rel}", data)
        items.append(
            f"<item><title><![CDATA[{rel}]]></title><pubDate>{date}</pubDate>"
            f'<media:content xmlns:media="http://video.search.yahoo.com/mrss/" url="x">'
            f'<media:hash algo="md5">{sha(data, "md5")}</media:hash></media:content></item>'
        )
    put(f"sf/{project}/rss{path}/feed.xml",
        f'<?xml version="1.0"?><rss version="2.0"><channel>{"".join(items)}</channel></rss>')


def targz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mode = 0o755
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


MANIFEST = """
[settings]
cache_dir = "{cache}"

[[category]]
id = "rescue"
dir = "2-Rescue"
title = "Linux Rescue"
description = "Linux rescue systems"

[[category]]
id = "diagnostics"
dir = "5-Diagnostics"
title = "Hardware Diagnostics"

[[category]]
id = "windows-pe"
dir = "1-Windows-PE"
title = "Windows PE"

[[tool]]
name = "ventoy"
title = "Ventoy"
kind = "ventoy"
source = "github"
repo = "ventoy/Ventoy"
asset = ['^ventoy-[\\d.]+-linux\\.tar\\.gz$']
version = 'ventoy-([\\d.]+)-linux'
checksum = [{{ asset = '^sha256\\.txt$' }}, "github-digest"]

[[tool]]
name = "systemrescue"
title = "SystemRescue"
kind = "iso"
category = "rescue"
source = "sourceforge"
project = "systemrescuecd"
path = "/sysresccd-x86"
asset = ['^systemrescue-[\\d.]+-amd64\\.iso$']
version = 'systemrescue-([\\d.]+)-amd64'
checksum = [{{ sibling = "{{name}}.sha512" }}, "sf-md5"]
description = "Rescue shell"

[[tool]]
name = "memtest86plus"
title = "Memtest86+"
kind = "iso"
category = "diagnostics"
source = "github"
repo = "memtest86plus/memtest86plus"
download_template = "{base}/memtest/download/v{{version}}/mt86plus_{{version}}_x86_64.iso.zip"
extract = '\\.iso$'
checksum = [{{ sibling = "sha512sum.txt" }}]

[[tool]]
name = "lazarus-pe"
title = "Lazarus PE"
kind = "iso"
category = "windows-pe"
source = "local"
path = "pe/out/LazarusPE.iso"

[[tool]]
name = "sysinternals"
title = "Sysinternals Suite"
kind = "app"
source = "url"
url = "{base}/web/SysinternalsSuite.zip"
entry = "procexp64.exe"
checksum = ["tofu"]
description = "Process Explorer | Autoruns   and more"
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="helix-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.stick = self.tmp / "stick"
        self.stick.mkdir()
        (self.repo / "tools.toml").write_text(MANIFEST.format(cache=self.tmp / "cache", base=BASE))
        (self.repo / "pe/launcher").mkdir(parents=True)
        shutil.copy2(ROOT / "pe/launcher/HelixApps.cmd", self.repo / "pe/launcher/")
        shutil.rmtree(WEB, ignore_errors=True)
        WEB.mkdir()
        # Upstream world, version 1
        # Like the real one: member names start with "./"
        self.ventoy_tgz = targz({"./ventoy-1.1.17/Ventoy2Disk.sh": b"#!/bin/sh\necho ventoy\n"})
        gh_release("ventoy/Ventoy", "v1.1.17", {
            "ventoy-1.1.17-linux.tar.gz": self.ventoy_tgz,
            "sha256.txt": f"{sha(self.ventoy_tgz)}  ventoy-1.1.17-linux.tar.gz\n".encode(),
        }, digests=False)
        self.sr_new = b"systemrescue 12.02 iso"
        sf_feed("systemrescuecd", "/sysresccd-x86", [
            ("/sysresccd-x86/12.01/systemrescue-12.01-amd64.iso", b"old", "Mon, 01 Jan 2024 10:00:00 UT"),
            ("/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso", self.sr_new, "Mon, 01 Jul 2024 10:00:00 UT"),
        ])
        put("dl/systemrescuecd/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso.sha512",
            f"{sha(self.sr_new, 'sha512')}  systemrescue-12.02-amd64.iso\n")
        gh_release("memtest86plus/memtest86plus", "v8.10", {})   # no assets: files live on memtest.org
        mz = zipped({"memtest.iso": b"memtest iso"})
        put("memtest/download/v8.10/mt86plus_8.10_x86_64.iso.zip", mz)
        put("memtest/download/v8.10/sha512sum.txt",
            f"{sha(b'x', 'sha512')}  mt86plus_8.10_i586.iso.zip\n{sha(mz, 'sha512')}  mt86plus_8.10_x86_64.iso.zip\n")
        put("web/SysinternalsSuite.zip", zipped({"procexp64.exe": b"MZ procexp", "Eula.txt": b"eula"}))
        self.cfg = cr.Config(repo=self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_quiet(self, fn, *a, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(*a, **kw)
        return rc, out.getvalue() + err.getvalue()

    def fetch(self, *names, force=False):
        ns = type("A", (), {"tools": list(names), "force": force})()
        return self.run_quiet(cr.cmd_fetch, self.cfg, ns)

    def sync(self, **kw):
        args = dict(target=str(self.stick), init=True, dry_run=False, verify=True, no_prune=False)
        args.update(kw)
        return self.run_quiet(cr.cmd_sync, self.cfg, type("A", (), args)())


class TestChecksumParsing(unittest.TestCase):
    def test_gnu_style(self):
        h = "a" * 64
        self.assertEqual(cr.parse_checksum_text(f"{h}  foo.iso\n{'b'*64}  bar.iso", "foo.iso"), ("sha256", h))

    def test_bsd_style(self):
        h = "c" * 128
        self.assertEqual(cr.parse_checksum_text(f"SHA512 (foo.iso) = {h}", "foo.iso"), ("sha512", h))

    def test_checksums_txt_picks_strongest(self):
        text = (f"### MD5SUMS:\n{'1'*32}  g.iso\n### SHA1SUMS:\n{'2'*40}  g.iso\n"
                f"### SHA256SUMS:\n{'3'*64}  g.iso\n{'4'*64}  other.iso\n")
        self.assertEqual(cr.parse_checksum_text(text, "g.iso"), ("sha256", "3" * 64))

    def test_bare_single_hash(self):
        self.assertEqual(cr.parse_checksum_text("D" * 64 + "\n", "x.iso"), ("sha256", "d" * 64))

    def test_nothing(self):
        self.assertIsNone(cr.parse_checksum_text(f"{'a'*64}  a\n{'b'*64}  b\n", "c"))


class TestVersions(unittest.TestCase):
    def test_clean_tag(self):
        self.assertEqual(cr.clean_tag("v8.10"), "8.10")
        self.assertEqual(cr.clean_tag("version-1.4.0"), "1.4.0")
        self.assertEqual(cr.clean_tag("v2025.11_31_x86-64_0.42"), "2025.11_31_x86-64_0.42")

    def test_multi_group_version(self):
        t = {"version": r"shredos-([\d.]+_\d+)_x86-64_v?([\d.]+)_"}
        self.assertEqual(cr._version(t, "shredos-2025.11_31_x86-64_v0.42_20260716.iso", None), "2025.11_31-0.42")


class TestConfig(Base):
    def test_missing_checksum_rejected(self):
        (self.repo / "tools.toml").write_text(
            (self.repo / "tools.toml").read_text().replace('checksum = ["tofu"]', ""))
        with self.assertRaisesRegex(cr.RescueError, "no checksum strategy"):
            cr.Config(repo=self.repo)

    def test_local_overrides(self):
        (self.repo / "local.toml").write_text('[overrides.memtest86plus]\nenabled = false\n')
        cfg = cr.Config(repo=self.repo)
        self.assertNotIn("memtest86plus", [t["name"] for t in cfg.enabled()])

    def test_url_file_override(self):
        put("fwlink/index.html", "redirect target stand-in")
        tool = {"name": "x", "title": "X", "kind": "app", "source": "url",
                "url": f"{BASE}/fwlink/?LinkId=1", "file": "msert.exe", "checksum": ["tofu"]}
        self.assertEqual(cr.resolve(tool, self.cfg)["file"], "msert.exe")
        del tool["file"]
        with self.assertRaisesRegex(cr.RescueError, "add file ="):
            cr.resolve(tool, self.cfg)

    def test_page_source_picks_newest_link(self):
        put("dlpage/index.html", '<a href="files/tool_75.iso">75</a> <a href="files/tool_lite_77.iso">lite</a>'
                                 '<a href="/dyna/?software=tool_76.iso&amp;x=1">76</a>')
        tool = {"name": "t", "title": "T", "kind": "iso", "category": "rescue", "source": "page",
                "page": f"{BASE}/dlpage/index.html", "asset": [r"tool_\d+\.iso$", r"tool_\d+\.iso"],
                "version": r"tool_(\d+)", "checksum": ["tofu"]}
        res = cr.resolve(tool, self.cfg)
        self.assertEqual((res["file"], res["version"]), ("tool_75.iso", "75"))  # first pattern with hits wins
        tool["asset"] = [r"tool_\d+\.iso"]
        res = cr.resolve(tool, self.cfg)
        self.assertEqual((res["file"], res["version"]), ("tool_76.iso", "76"))
        self.assertEqual(res["url"], f"{BASE}/dyna/?software=tool_76.iso&x=1")

    def test_sourceforge_unversioned_file_uses_upload_date(self):
        sf_feed("brd", "/", [("/brd-64bit.iso", b"iso", "Sat, 23 Dec 2023 11:59:10 UT")])
        tool = {"name": "brd", "title": "BRD", "kind": "iso", "category": "rescue", "source": "sourceforge",
                "project": "brd", "path": "/", "asset": [r"^brd-64bit\.iso$"], "checksum": ["sf-md5"]}
        self.assertEqual(cr.resolve(tool, self.cfg)["version"], "2023-12-23")

    def test_unknown_override(self):
        (self.repo / "local.toml").write_text('[overrides.nope]\nenabled = false\n')
        with self.assertRaisesRegex(cr.RescueError, "unknown tool"):
            cr.Config(repo=self.repo)

    def test_shipped_manifest_is_valid(self):
        cfg = cr.Config(repo=ROOT, manifest=ROOT / "tools.toml")
        self.assertGreater(len(cfg.tools), 10)

    def test_every_category_and_boot_tool_has_an_icon(self):
        # theme/icons is generated by theme/build-theme.py; rerun it after adding a tool or category
        cfg = cr.Config(repo=ROOT, manifest=ROOT / "tools.toml")
        have = {p.stem for p in (ROOT / "theme/icons").glob("*.png")}
        want = {f"cat-{c}" for c in cfg.categories} | {t["name"] for t in cfg.tools if t["kind"] == "iso"}
        want |= {"vtoydir", "vtoyret", "vtoyiso"}
        self.assertEqual(sorted(want - have), [], "run theme/build-theme.py")


class TestFetchAndSync(Base):
    def test_full_flow(self):
        rc, out = self.fetch()
        self.assertEqual(rc, 0, out)
        self.assertIn("isn't built yet", out)                      # local PE skipped, not failed
        lock = cr.load_lock(self.cfg)
        self.assertEqual(lock["systemrescue"]["version"], "12.02")  # newest by date
        self.assertIn("sha512", lock["systemrescue"]["verified_by"])
        self.assertEqual(lock["ventoy"]["final"], "ventoy-1.1.17")
        self.assertIn("sha256.txt", lock["ventoy"]["verified_by"])
        self.assertEqual(lock["memtest86plus"]["final"], "memtest.iso")
        self.assertEqual(lock["memtest86plus"]["version"], "8.10")
        self.assertIn("sha512sum.txt", lock["memtest86plus"]["verified_by"])
        self.assertEqual(lock["sysinternals"]["verified_by"], "unverified (trust on first use)")

        # second run: everything current, nothing re-downloaded
        rc, out = self.fetch()
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count("up to date"), 4, out)

        rc, out = self.run_quiet(cr.cmd_ventoy_path, self.cfg, None)
        self.assertTrue(out.strip().endswith("ventoy-1.1.17"), out)

        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        iso = self.stick / "ISO/2-Rescue/systemrescue-12.02-amd64.iso"
        self.assertEqual(iso.read_bytes(), self.sr_new)
        self.assertTrue((self.stick / "ISO/5-Diagnostics/memtest.iso").exists())
        self.assertTrue((self.stick / "Apps/sysinternals/procexp64.exe").exists())
        self.assertEqual((self.stick / "Apps/apps.txt").read_bytes(),
                         b"Sysinternals Suite|sysinternals\\procexp64.exe|Process Explorer / Autoruns and more\r\n")
        self.assertTrue((self.stick / "Apps/HelixApps.cmd").exists())
        vj = json.loads((self.stick / "ventoy/ventoy.json").read_text())
        aliases = {a.get("dir") or a.get("image"): a["alias"] for a in vj["menu_alias"]}
        self.assertEqual(aliases["/ISO/2-Rescue"], "Linux Rescue  →")
        tips = {t.get("dir") or t.get("image"): t["tip"] for t in vj["menu_tip"]["tips"]}
        self.assertEqual(tips["/ISO/2-Rescue"], "Linux rescue systems")
        self.assertIn("→", (self.stick / "ventoy/ventoy.json").read_text(encoding="utf-8"))  # not \u2192
        self.assertEqual(aliases["/ISO/2-Rescue/systemrescue-12.02-amd64.iso"], "SystemRescue")  # no version: cleaner menu
        self.assertNotIn("/ISO/1-Windows-PE", aliases)             # empty category hidden
        self.assertTrue((self.stick / "helix-boot.tag").exists())
        self.assertTrue((self.stick / "commander-rescue.tag").exists())   # for launchers and PEs from before

        # user file on the stick must survive syncs
        mine = self.stick / "ISO/2-Rescue/my-own.iso"
        mine.write_bytes(b"mine")

        # upstream ships 12.03 → fetch replaces cache, sync prunes 12.02 only
        new = b"systemrescue 12.03 iso"
        put("dl/systemrescuecd/sysresccd-x86/12.03/systemrescue-12.03-amd64.iso.sha512",
            f"{sha(new, 'sha512')}  systemrescue-12.03-amd64.iso\n")
        sf_feed("systemrescuecd", "/sysresccd-x86", [
            ("/sysresccd-x86/12.03/systemrescue-12.03-amd64.iso", new, "Mon, 01 Sep 2025 10:00:00 UT"),
            ("/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso", self.sr_new, "Mon, 01 Jul 2024 10:00:00 UT"),
        ])
        rc, out = self.fetch("systemrescue")
        self.assertEqual(rc, 0, out)
        self.assertEqual([p.name for p in (self.tmp / "cache/systemrescue").iterdir()],
                         ["systemrescue-12.03-amd64.iso"])
        rc, out = self.sync(init=False)
        self.assertEqual(rc, 0, out)
        self.assertFalse(iso.exists())
        self.assertTrue((self.stick / "ISO/2-Rescue/systemrescue-12.03-amd64.iso").exists())
        self.assertTrue(mine.exists())

    def test_checksum_mismatch_is_refused(self):
        put("dl/systemrescuecd/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso.sha512",
            f"{'0'*128}  systemrescue-12.02-amd64.iso\n")
        rc, out = self.fetch("systemrescue")
        self.assertEqual(rc, 1)
        self.assertIn("checksum MISMATCH", out)
        self.assertFalse((self.tmp / "cache/systemrescue/systemrescue-12.02-amd64.iso").exists())

    def test_falls_back_to_sf_md5(self):
        (WEB / "dl/systemrescuecd/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso.sha512").unlink()
        rc, out = self.fetch("systemrescue")
        self.assertEqual(rc, 0, out)
        self.assertIn("md5", cr.load_lock(self.cfg)["systemrescue"]["verified_by"])

    def test_sourceforge_md5_must_agree_with_a_mirror_checksum(self):
        # F10: a mirror serving a changed file with a matching .sha512 beside it
        bad = b"systemrescue 12.02 iso, changed by a mirror"
        put("dl/systemrescuecd/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso", bad)
        put("dl/systemrescuecd/sysresccd-x86/12.02/systemrescue-12.02-amd64.iso.sha512",
            f"{sha(bad, 'sha512')}  systemrescue-12.02-amd64.iso\n")
        rc, out = self.fetch("systemrescue")
        self.assertEqual(rc, 1, out)
        self.assertIn("doesn't match the md5 SourceForge publishes", out)
        self.assertFalse((self.tmp / "cache/systemrescue/systemrescue-12.02-amd64.iso").exists())

    def test_sourceforge_download_records_both_checks(self):
        rc, out = self.fetch("systemrescue")
        self.assertEqual(rc, 0, out)
        self.assertIn("+ SourceForge md5", cr.load_lock(self.cfg)["systemrescue"]["verified_by"])

    def test_no_checksum_refused_without_tofu(self):
        gh_release("ventoy/Ventoy", "v1.1.18",
                   {"ventoy-1.1.18-linux.tar.gz": self.ventoy_tgz}, digests=False)
        rc, out = self.fetch("ventoy")
        self.assertEqual(rc, 1)
        self.assertIn("couldn't find an upstream checksum", out)

    def test_unversioned_url_redownloads_when_changed(self):
        self.fetch("sysinternals")
        v1 = cr.load_lock(self.cfg)["sysinternals"]["version"]
        rc, out = self.fetch("sysinternals")
        self.assertIn("up to date", out)
        import time
        time.sleep(1.1)  # Last-Modified has 1s resolution
        put("web/SysinternalsSuite.zip", zipped({"procexp64.exe": b"MZ procexp v2 longer"}))
        rc, out = self.fetch("sysinternals")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("up to date", out)
        self.assertNotEqual(cr.load_lock(self.cfg)["sysinternals"]["version"], v1)

    def test_local_pe_build_is_picked_up(self):
        pe = self.repo / "pe/out/LazarusPE.iso"
        pe.parent.mkdir(parents=True)
        pe.write_bytes(b"winpe")
        rc, out = self.fetch("lazarus-pe")
        self.assertEqual(rc, 0, out)
        self.fetch("systemrescue")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.stick / "ISO/1-Windows-PE/LazarusPE.iso").read_bytes(), b"winpe")

    def test_same_size_rebuild_is_copied_without_verify(self):
        pe = self.repo / "pe/out/LazarusPE.iso"
        pe.parent.mkdir(parents=True)
        on_stick = self.stick / "ISO/1-Windows-PE/LazarusPE.iso"
        for n, build in enumerate((b"winpe-1", b"winpe-2")):   # same size, different build
            pe.write_bytes(build)
            self.fetch("lazarus-pe")
            rc, out = self.sync(verify=False, init=n == 0)
            self.assertEqual(rc, 0, out)
            self.assertEqual(on_stick.read_bytes(), build)
        rc, out = self.sync(verify=False, init=False)
        self.assertIn("Lazarus PE 20", out)
        self.assertIn("already on stick", out)

        # A stick synced before image checksums were recorded: a newer local build is still noticed
        state_file = self.stick / ".helix-boot/state.json"
        state = json.loads(state_file.read_text())
        del state["images"]
        state_file.write_text(json.dumps(state))
        pe.write_bytes(b"winpe-3")
        self.fetch("lazarus-pe")
        rc, out = self.sync(verify=False, init=False)
        self.assertEqual(rc, 0, out)
        self.assertEqual(on_stick.read_bytes(), b"winpe-3")

    def test_lazarus_launcher_goes_into_apps(self):
        shutil.copytree(ROOT / "pe/lazarus", self.repo / "pe/lazarus")
        self.fetch("sysinternals")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        got = sorted(p.name for p in (self.stick / "Apps/Lazarus").iterdir())
        want = sorted(p.name for p in (ROOT / "pe/lazarus").iterdir() if p.suffix != ".md")
        self.assertEqual(got, want)
        self.assertIn("LazarusLauncher.ps1", got)
        # Windows PowerShell 5.1 reads a .ps1 without a BOM as ANSI, mangling its … and ·
        self.assertTrue((self.stick / "Apps/Lazarus/LazarusLauncher.ps1").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_sync_refuses_non_ventoy_without_init(self):
        self.fetch("systemrescue")
        with self.assertRaisesRegex(cr.RescueError, "doesn't look like a Ventoy stick"):
            cr.cmd_sync(self.cfg, type("A", (), dict(target=str(self.stick), init=False, dry_run=False,
                                                     verify=False, no_prune=False))())

    def test_user_category_is_labelled_even_without_tools(self):
        with open(self.repo / "tools.toml", "a") as f:
            f.write('\n[[category]]\nid = "images"\ndir = "OSimages"\ntitle = "OS Images"\n'
                    'description = "Installers you add yourself."\nuser = true\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue")
        mine = self.stick / "ISO/OSimages/Win11.iso"
        mine.parent.mkdir(parents=True)
        mine.write_bytes(b"mine")
        (self.stick / "ISO/OSimages/ReadMe.txt").write_bytes(b"your notes")   # FAT ignores case: keep off it
        for _ in range(2):                                          # second sync: nothing of yours pruned
            rc, out = self.sync(init=_ == 0)
            self.assertEqual(rc, 0, out)
        vj = json.loads((self.stick / "ventoy/ventoy.json").read_text())
        aliases = {a.get("dir") or a.get("image"): a["alias"] for a in vj["menu_alias"]}
        self.assertEqual(aliases["/ISO/OSimages"], "OS Images  →")
        tips = {t.get("dir") or t.get("image"): t["tip"] for t in vj["menu_tip"]["tips"]}
        self.assertEqual(tips["/ISO/OSimages"], "Installers you add yourself.")
        self.assertIn(b"stays hidden", (self.stick / "ISO/OSimages/HELIX-BOOT.txt").read_bytes())
        self.assertEqual(mine.read_bytes(), b"mine")
        self.assertEqual((self.stick / "ISO/OSimages/ReadMe.txt").read_bytes(), b"your notes")
        self.assertNotIn("/ISO/1-Windows-PE", aliases)             # ordinary empty categories still hidden

    def test_existing_ventoy_json_is_backed_up(self):
        self.fetch("systemrescue")
        (self.stick / "ventoy").mkdir()
        (self.stick / "ventoy/ventoy.json").write_text('{"mine": true}')
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        backups = list((self.stick / "ventoy").glob("ventoy.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{"mine": true}')

    def splash(self, efi, **kw):
        args = dict(efi=str(efi), remove=False, dry_run=False)
        args.update(kw)
        return self.run_quiet(cr.cmd_splash, self.cfg, type("A", (), args)())

    def test_splash_before_the_ventoy_menu(self):
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        efi = self.tmp / "VTOYEFI"
        (efi / "grub").mkdir(parents=True)
        original = ("#Main stuff\nterminal_output gfxterm\n\n# 中文 note\n"
                    "#clear all input key before show main menu\nvt_clear_key\n\nvt_dynamic_menu 0 1\n")
        script = efi / "grub" / "grub.cfg"
        script.write_text(original, encoding="utf-8")

        rc, out = self.splash(efi, dry_run=True)
        self.assertEqual((rc, script.read_text(encoding="utf-8")), (0, original))
        rc, out = self.splash(efi)
        self.assertEqual(rc, 0, out)
        once = script.read_text(encoding="utf-8")
        self.assertEqual(once.count(cr.SPLASH_BEGIN), 1)
        self.assertIn("sleep --interruptible 1\n", once)
        self.assertLess(once.index(cr.SPLASH_END), once.index("#clear all input key"))   # before the menu
        self.assertIn("# 中文 note", once)
        rc, out = self.splash(efi)                                   # again: nothing changes
        self.assertEqual(script.read_text(encoding="utf-8"), once)
        self.assertIn("already", out)

        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\nsplash_seconds = 3\n')
        self.cfg = cr.Config(repo=self.repo)
        self.splash(efi)
        three = script.read_text(encoding="utf-8")
        self.assertEqual(three.count(cr.SPLASH_BEGIN), 1)
        self.assertIn("sleep --interruptible 3\n", three)
        self.assertIn("for r in 1 2 3; do\n", three)          # each loading-bar frame drawn 3 times

        self.splash(efi, remove=True)
        self.assertEqual(script.read_text(encoding="utf-8"), original)     # taken out cleanly
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\nsplash_seconds = 0\n')
        self.cfg = cr.Config(repo=self.repo)
        self.splash(efi)
        self.assertEqual(script.read_text(encoding="utf-8"), original)
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\nsplash_seconds = 99\n')
        self.cfg = cr.Config(repo=self.repo)
        with self.assertRaisesRegex(cr.RescueError, "between 0"):
            self.splash(efi)

    def test_splash_leaves_an_unknown_ventoy_alone(self):
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        efi = self.tmp / "VTOYEFI"
        (efi / "grub").mkdir(parents=True)
        (efi / "grub" / "grub.cfg").write_text("vt_dynamic_menu 0 1\n")
        rc, out = self.splash(efi)
        self.assertEqual(rc, 0, out)
        self.assertIn("isn't laid out as expected", out)
        self.assertEqual((efi / "grub" / "grub.cfg").read_text(), "vt_dynamic_menu 0 1\n")
        with self.assertRaisesRegex(cr.RescueError, "isn't Ventoy's boot partition"):
            self.splash(self.tmp)

    def test_your_own_splash_picture(self):
        theme = self.repo / "theme"
        theme.mkdir()
        (theme / "theme.txt").write_text('desktop-image: "background.png"\n')
        (theme / "splash.png").write_bytes(b"theme splash")
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue")
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual((self.stick / "ventoy/theme/splash.png").read_bytes(), b"theme splash")
        (self.repo / "byo").mkdir(exist_ok=True)
        (self.repo / "byo" / "splash.png").write_bytes(b"my splash")
        self.assertEqual(self.sync(init=False)[0], 0)
        self.assertEqual((self.stick / "ventoy/theme/splash.png").read_bytes(), b"my splash")

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "the loading bar needs Pillow")
    def test_splash_loading_bar_frames(self):
        from PIL import Image
        theme = self.repo / "theme"
        theme.mkdir()
        (theme / "theme.txt").write_text('desktop-image: "background.png"\n')
        Image.new("RGB", (64, 36), (20, 10, 40)).save(theme / "splash.png")
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue")
        self.assertEqual(self.sync()[0], 0)
        frames = sorted((self.stick / "ventoy/theme/splash").iterdir())
        self.assertEqual([f.name for f in frames], [f"{k:02d}.jpg" for k in range(cr.SPLASH_FRAMES + 1)])
        with Image.open(frames[0]) as first, Image.open(frames[-1]) as last:
            self.assertEqual((first.format, first.size), ("JPEG", (1920, 1080)))
            self.assertLess(first.getpixel((700, 1004))[1], 100)    # empty bar …
            self.assertGreater(last.getpixel((700, 1004))[1], 150)  # … full, cyan at the left
        cached = list((self.cfg.cache / "splash").iterdir())
        Image.new("RGB", (64, 36), (40, 10, 20)).save(theme / "splash.png")    # a new picture
        self.assertEqual(self.sync(init=False)[0], 0)
        now = set((self.cfg.cache / "splash").iterdir())
        self.assertEqual(len(now - set(cached)), 1)                      # redrawn for the new picture
        self.assertEqual((self.stick / cr.THEME_SRC / "splash/for.txt").read_text(), (now - set(cached)).pop().name)

    def test_oversized_icons_are_flagged(self):
        import struct
        def png(w, h):
            return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x06\0\0\0"
        theme = self.repo / "theme"
        (theme / "icons").mkdir(parents=True)
        (theme / "theme.txt").write_text('desktop-image: "background.png"\n')
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        mine = self.repo / "byo" / "icons"
        mine.mkdir(parents=True)
        (mine / "systemrescue.png").write_bytes(png(40, 40))
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("--fit-icons", out)
        (mine / "gparted.png").write_bytes(png(1254, 1254))
        (mine / "originals").mkdir()
        (mine / "originals" / "huge.png").write_bytes(png(4000, 4000))   # kept, never copied or flagged
        rc, out = self.sync(init=False)
        self.assertEqual(rc, 0, out)
        self.assertIn("1 of your icons in byo/icons/ are much bigger", out)
        self.assertIn("gparted.png, 1254x1254", out)
        self.assertFalse((self.stick / "ventoy/theme/icons/huge.png").exists())

    def test_theme_is_copied_and_wired_up(self):
        theme = self.repo / "theme"
        (theme / "fonts").mkdir(parents=True)
        (theme / "theme.txt").write_text("desktop-image: \"background.png\"\n")
        (theme / "fonts/b.pf2").write_bytes(b"PFF2")
        (theme / "fonts/a.pf2").write_bytes(b"PFF2")
        (theme / "build-theme.py").write_text("# generator, not for the stick\n")
        (theme / "__pycache__").mkdir()
        (theme / "__pycache__/build-theme.cpython-311.pyc").write_bytes(b"pyc")
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue")
        (self.stick / "ventoy/theme").mkdir(parents=True)
        (self.stick / "ventoy/theme/stale.png").write_bytes(b"old")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        on_stick = sorted(p.relative_to(self.stick / "ventoy/theme").as_posix()
                          for p in (self.stick / "ventoy/theme").rglob("*") if p.is_file())
        self.assertEqual(on_stick, ["fonts/a.pf2", "fonts/b.pf2", "theme.txt"])
        vj = json.loads((self.stick / "ventoy/ventoy.json").read_text())
        self.assertEqual(vj["theme"]["file"], "/ventoy/theme/theme.txt")
        self.assertEqual(vj["theme"]["fonts"], ["/ventoy/theme/fonts/a.pf2", "/ventoy/theme/fonts/b.pf2"])
        # The tip must sit below the new left-side menu; the version must not cover navigation.
        self.assertEqual(vj["menu_tip"]["left"], "5%")
        self.assertEqual(vj["menu_tip"]["top"], "82%")
        self.assertEqual(vj["menu_tip"]["color"], "#baabd3")
        self.assertEqual(vj["theme"]["ventoy_top"], "94%")

    def test_menu_icons(self):
        theme = self.repo / "theme"
        (theme / "icons").mkdir(parents=True)
        (theme / "theme.txt").write_text("")
        for name in ("cat-rescue", "systemrescue", "memtest86plus", "vtoydir"):
            (theme / f"icons/{name}.png").write_bytes(b"theme icon")
        (self.repo / "byo/icons").mkdir(parents=True)
        (self.repo / "byo/icons/systemrescue.png").write_bytes(b"my logo")
        (self.repo / "byo/icons/cat-diagnostics.png").write_bytes(b"my category icon")
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue", "memtest86plus", "lazarus-pe")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        icons = self.stick / "ventoy/theme/icons"
        self.assertEqual((icons / "systemrescue.png").read_bytes(), b"my logo")      # yours win
        self.assertEqual((icons / "memtest86plus.png").read_bytes(), b"theme icon")
        self.assertTrue((icons / "cat-diagnostics.png").exists())
        classes = json.loads((self.stick / "ventoy/ventoy.json").read_text())["menu_class"]
        self.assertIn({"dir": "/ISO/2-Rescue", "class": "cat-rescue"}, classes)
        self.assertIn({"dir": "/ISO/5-Diagnostics", "class": "cat-diagnostics"}, classes)
        keys = [c for c in classes if "key" in c]
        # Ventoy wants a key shorter than the file name, so the extension is dropped
        self.assertIn({"key": "systemrescue-12.02-amd64", "class": "systemrescue"}, keys)
        self.assertIn({"key": "memtest", "class": "memtest86plus"}, keys)
        self.assertEqual(keys, sorted(keys, key=lambda k: -len(k["key"])))
        for c in keys:
            self.assertTrue(any(c["key"] in f.name and len(c["key"]) < len(f.name)
                                for f in (self.stick / "ISO").rglob("*.iso")), c)

    def look(self, **kw):
        args = dict(stick=str(self.stick), theme=None, icons=None, background=None, dim=0, splash=None,
                    reset=False, json=False, menu=False, preview=None)
        args.update(kw)
        return self.run_quiet(cr.cmd_theme, self.cfg, type("A", (), args)())

    def themed_repo(self):
        """A theme with one preset ("night") and one icon pack ("badges"), synced to the stick."""
        theme = self.repo / "theme"
        for d in ("icons", "presets/night/icons", "icon-packs/badges"):
            (theme / d).mkdir(parents=True)
        (theme / "theme.txt").write_text('desktop-image: "background.png"\n+ boot_menu {\n'
                                         '  icon_width = 40    # icons\n  icon_height = 40\n  item_icon_space = 16\n}\n')
        (theme / "background.png").write_bytes(b"default background")
        (theme / "splash.png").write_bytes(b"default splash")
        (theme / "preset.toml").write_text('title = "Neon"\nmuted = "#baabd3"\n')
        for name in ("systemrescue", "vtoydir"):
            (theme / f"icons/{name}.png").write_bytes(b"theme icon")
        night = theme / "presets/night"
        (night / "theme.txt").write_text('desktop-image: "background.png"\n# night\n')
        (night / "background.png").write_bytes(b"night background")
        (night / "splash.png").write_bytes(b"night splash")
        (night / "preset.toml").write_text('title = "Night"\ndescription = "Dark."\nmuted = "#112233"\n'
                                           'bar = ["#010203", "#040506"]\n')
        (night / "icons/vtoydir.png").write_bytes(b"night icon")
        (theme / "icon-packs/badges/systemrescue.png").write_bytes(b"badge")
        (theme / "icon-packs/badges/pack.toml").write_text('title = "Letter badges"\n')
        (self.repo / "local.toml").write_text('[settings]\ntheme = "theme"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        return self.stick / "ventoy/theme", lambda: json.loads((self.stick / "ventoy/ventoy.json").read_text())

    def test_theme_presets_icon_packs_and_off(self):
        built, menu = self.themed_repo()
        default = (self.stick / "ventoy/ventoy.json").read_bytes()
        self.assertEqual(default, (self.stick / cr.BASE_JSON).read_bytes())   # the default look changes nothing
        self.assertEqual((built / "background.png").read_bytes(), b"default background")
        self.assertFalse((built / "presets").exists() or (built / "icon-packs").exists() or (built / "preset.toml").exists())

        rc, out = self.look()                                            # just looking
        self.assertEqual(rc, 0, out)
        for text in ("Neon (default)", "night", "Night: Dark.", "badges", "Letter badges"):
            self.assertIn(text, out)
        self.assertFalse((self.stick / cr.LOOK_FILE).exists())

        rc, out = self.look(theme="night")
        self.assertEqual(rc, 0, out)
        self.assertEqual((built / "background.png").read_bytes(), b"night background")
        self.assertIn("# night", (built / "theme.txt").read_text())
        self.assertEqual((built / "splash.png").read_bytes(), b"night splash")
        self.assertEqual((built / "icons/vtoydir.png").read_bytes(), b"night icon")       # recoloured
        self.assertEqual((built / "icons/systemrescue.png").read_bytes(), b"theme icon")  # logos stay
        self.assertEqual((menu()["theme"]["ventoy_color"], menu()["menu_tip"]["color"]), ("#112233", "#112233"))
        self.assertEqual(self.sync(init=False)[0], 0)                    # a refresh keeps the look …
        self.assertEqual((built / "background.png").read_bytes(), b"night background")
        self.assertEqual(list((self.stick / "ventoy").glob("ventoy.json.bak-*")), [])     # … and it isn't "edited"

        self.look(icons="badges")
        self.assertEqual((built / "icons/systemrescue.png").read_bytes(), b"badge")
        self.assertFalse((built / "icons/pack.toml").exists())
        self.look(icons="off")
        self.assertFalse((built / "icons").exists())
        self.assertNotIn("menu_class", menu())
        self.look(theme="default")                                       # … and no gap where they were
        self.assertIn("icon_width = 0    # icons\n  icon_height = 0\n  item_icon_space = 0\n", (built / "theme.txt").read_text())

        rc, out = self.look(theme="off")
        self.assertEqual(rc, 0, out)
        self.assertFalse(built.exists())                                 # no theme, and no splash of its either
        self.assertNotIn("theme", menu())
        self.assertEqual((menu()["menu_tip"]["left"], menu()["menu_tip"]["color"]), ("10%", "#7fb4ff"))
        self.assertEqual(self.sync(init=False)[0], 0)
        self.assertNotIn("theme", menu())

        rc, out = self.look(reset=True)
        self.assertEqual((self.stick / "ventoy/ventoy.json").read_bytes(), default)
        self.assertEqual((built / "background.png").read_bytes(), b"default background")
        self.assertEqual((built / "icons/systemrescue.png").read_bytes(), b"theme icon")

        with self.assertRaisesRegex(cr.RescueError, "no theme called 'nope'"):
            self.look(theme="nope")
        with self.assertRaisesRegex(cr.RescueError, "no icon pack called"):
            self.look(icons="../x")
        with self.assertRaisesRegex(cr.RescueError, "--dim goes with"):
            self.look(dim=40)
        rc, out = self.look(json=True)
        report = json.loads(out)
        self.assertEqual(report["look"], cr.LOOK_DEFAULT)
        self.assertEqual([t["id"] for t in report["themes"]], ["default", "night", "off"])
        self.assertEqual([t["id"] for t in report["icon_packs"]], ["logos", "badges", "off"])

    def test_your_own_splash_and_icons_beat_a_preset(self):
        (self.repo / "byo/icons").mkdir(parents=True)
        (self.repo / "byo/icons/vtoydir.png").write_bytes(b"my folder icon")
        (self.repo / "byo/splash.png").write_bytes(b"my splash")
        built, menu = self.themed_repo()
        self.look(theme="night")
        self.assertEqual((built / "icons/vtoydir.png").read_bytes(), b"my folder icon")
        self.assertEqual((built / "splash.png").read_bytes(), b"my splash")
        self.look(splash="theme")
        self.assertEqual((built / "splash.png").read_bytes(), b"night splash")
        self.look(splash="off")
        self.assertFalse((built / "splash.png").exists())
        self.look(theme="off", splash="auto")                            # your own picture still shows
        self.assertEqual(sorted(f.name for f in built.iterdir()), ["splash.png"])

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "resizing a picture needs Pillow")
    def test_your_own_background(self):
        from PIL import Image
        built, menu = self.themed_repo()
        picture = self.tmp / "holiday.jpg"
        Image.new("RGB", (800, 600), (200, 100, 50)).save(picture)
        rc, out = self.look(background=str(picture), dim=50)
        self.assertEqual(rc, 0, out)
        with Image.open(built / "background.png") as im:
            self.assertEqual((im.format, im.size, im.getpixel((5, 5))), ("PNG", (1920, 1080), (100, 50, 25)))
        self.assertEqual(self.sync(init=False)[0], 0)                    # kept on the stick, not in the repo
        with Image.open(built / "background.png") as im:
            self.assertEqual(im.size, (1920, 1080))
        self.look(theme="night")                                         # … and over any preset
        with Image.open(built / "background.png") as im:
            self.assertEqual(im.size, (1920, 1080))
        self.look(background="theme")
        self.assertEqual((built / "background.png").read_bytes(), b"night background")
        self.look(background="custom")                                   # the one already on the stick again
        with Image.open(built / "background.png") as im:
            self.assertEqual(im.size, (1920, 1080))
        with self.assertRaisesRegex(cr.RescueError, "no splash picture of yours"):
            self.look(splash="custom")
        preview = self.tmp / "preview.png"
        before = (self.stick / cr.LOOK_FILE).read_text()
        rc, out = self.look(theme="off", preview=str(preview))           # a picture only: the stick is untouched
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.stick / cr.LOOK_FILE).read_text(), before)
        self.look(theme="night", preview=str(preview))
        with Image.open(preview) as im:
            self.assertEqual(im.size, (960, 540))
        with self.assertRaisesRegex(cr.RescueError, "neither a picture file"):
            self.look(background=str(self.tmp / "missing.png"))

    def test_look_needs_a_stick_from_this_version(self):
        self.fetch("systemrescue")
        self.assertEqual(self.sync()[0], 0)
        (self.stick / cr.BASE_JSON).unlink()                             # as an older Helix Boot left it
        with self.assertRaisesRegex(cr.RescueError, "older Helix Boot"):
            self.look(theme="off")
        # a pack from before `helix theme` brings its theme and menu ready-made: they're used as they are
        (self.stick / cr.THEME_SRC).mkdir(parents=True)
        (self.stick / cr.THEME_SRC / "theme.txt").write_text("stale")
        (self.stick / cr.BASE_JSON).write_text("{}")
        cr._write_extras(self.cfg, self.stick, {}, [("ventoy/theme/theme.txt", b"from the pack"),
                                                    ("ventoy/ventoy.json", b'{"pack": true}')], True)
        self.assertFalse((self.stick / cr.THEME_SRC).exists())
        self.assertEqual((self.stick / "ventoy/theme/theme.txt").read_bytes(), b"from the pack")
        self.assertEqual((self.stick / "ventoy/ventoy.json").read_bytes(), b'{"pack": true}')

    def test_no_icons_without_theme(self):
        (self.repo / "byo/icons").mkdir(parents=True)
        (self.repo / "byo/icons/systemrescue.png").write_bytes(b"my logo")
        self.fetch("systemrescue")
        self.assertEqual(self.sync()[0], 0)
        self.assertNotIn("menu_class", json.loads((self.stick / "ventoy/ventoy.json").read_text()))

    def test_renamed_category_moves_files_instead_of_copying(self):
        self.fetch("systemrescue", "memtest86plus")
        self.assertEqual(self.sync()[0], 0)
        mine = self.stick / "ISO/2-Rescue/my-own.iso"
        mine.write_bytes(b"mine")
        (self.repo / "tools.toml").write_text((self.repo / "tools.toml").read_text()
                                              .replace('dir = "5-Diagnostics"', 'dir = "4-Diagnostic-Tools"')
                                              .replace('dir = "2-Rescue"', 'dir = "6-Live"'))
        self.cfg = cr.Config(repo=self.repo)
        with unittest.mock.patch.object(cr, "_copy", side_effect=AssertionError("copied again")):
            rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        self.assertIn("moving", out)
        self.assertTrue((self.stick / "ISO/4-Diagnostic-Tools/memtest.iso").exists())
        self.assertEqual((self.stick / "ISO/6-Live/systemrescue-12.02-amd64.iso").read_bytes(), self.sr_new)
        self.assertFalse((self.stick / "ISO/5-Diagnostics").exists())          # emptied, removed
        self.assertTrue(mine.exists())                                          # yours stay put
        self.assertTrue((self.stick / "ISO").is_dir())

    def test_old_category_ids_still_work(self):
        (self.repo / "tools.toml").write_text((self.repo / "tools.toml").read_text()
                                              .replace('id = "rescue"', 'id = "live"')
                                              .replace('category = "rescue"', 'category = "live"'))
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "mine"\ntitle = "Mine"\nkind = "iso"\ncategory = "rescue"\n'
            'source = "local"\npath = "byo/mine.iso"\n')
        cfg = cr.Config(repo=self.repo)
        self.assertEqual({t["name"]: t.get("category") for t in cfg.tools}["mine"], "live")

    def test_no_theme_setting_means_no_theme(self):
        self.fetch("systemrescue")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("theme", json.loads((self.stick / "ventoy/ventoy.json").read_text()))
        self.assertFalse((self.stick / "ventoy/theme").exists())

    def test_bring_your_own_slot(self):
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "mine"\ntitle = "Mine"\nkind = "iso"\ncategory = "rescue"\n'
            'source = "local"\nbyo = true\npath = "byo/mine.iso"\n')
        self.cfg = cr.Config(repo=self.repo)
        rc, out = self.fetch("mine")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Mine", out)                      # empty slot: silent
        (self.repo / "byo").mkdir()
        (self.repo / "byo/mine.iso").write_bytes(b"licensed iso")
        rc, out = self.fetch("mine")
        self.assertIn("your own file registered", out)
        self.assertEqual(self.sync()[0], 0)
        placed = list(self.stick.rglob("mine.iso"))
        self.assertEqual(len(placed), 1)
        (self.repo / "byo/mine.iso").unlink()               # taken away again
        self.fetch("mine")
        self.assertNotIn("mine", cr.load_lock(self.cfg))
        self.assertEqual(self.sync()[0], 0)
        self.assertFalse(placed[0].exists())

    def test_check_json_stays_clean_when_warning(self):
        Quiet.fail["/sf/systemrescuecd/rss/sysresccd-x86/feed.xml"] = 1   # forces a retry warning
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                cr.cmd_check(self.cfg, type("A", (), {"tools": ["systemrescue"], "json": True})())
        finally:
            Quiet.fail.clear()
        self.assertIn("retrying", err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["systemrescue"]["latest"], "12.02")

    def test_bring_your_own_apps(self):
        (self.repo / "byo").mkdir()
        (self.repo / "byo/Trial.exe").write_bytes(b"MZ trial")
        (self.repo / "byo/suite.zip").write_bytes(zipped({"Suite/suite.exe": b"MZ suite"}))
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "trial"\ntitle = "Trial Tool"\nkind = "app"\nsource = "local"\nbyo = true\n'
            'path = "byo/Trial.exe"\nentry = "Trial.exe"\n\n'
            '[[tool]]\nname = "suite"\ntitle = "Suite"\nkind = "app"\nsource = "local"\nbyo = true\n'
            'path = "byo/suite.zip"\nentry = "Suite/suite.exe"\n\n'
            '[[tool]]\nname = "empty"\ntitle = "Empty Slot"\nkind = "app"\nsource = "local"\nbyo = true\n'
            'path = "byo/none.exe"\nentry = "none.exe"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("systemrescue", "trial", "suite", "empty")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Empty Slot", out)
        self.assertEqual((self.stick / "Apps/trial/Trial.exe").read_bytes(), b"MZ trial")
        self.assertEqual((self.stick / "Apps/suite/Suite/suite.exe").read_bytes(), b"MZ suite")
        apps = (self.stick / "Apps/apps.txt").read_text()
        self.assertIn("Trial Tool|trial\\Trial.exe", apps)
        self.assertIn("Suite|suite\\Suite\\suite.exe", apps)

    def test_windows_gets_the_windows_ventoy_package(self):
        wzip = zipped({"ventoy-1.1.17/Ventoy2Disk.exe": b"MZ ventoy", "ventoy-1.1.17/ventoy/x.bin": b"x"})
        gh_release("ventoy/Ventoy", "v1.1.17", {
            "ventoy-1.1.17-linux.tar.gz": self.ventoy_tgz,
            "ventoy-1.1.17-windows.zip": wzip,
            "sha256.txt": f"{sha(self.ventoy_tgz)}  ventoy-1.1.17-linux.tar.gz\n"
                          f"{sha(wzip)}  ventoy-1.1.17-windows.zip\n".encode(),
        }, digests=False)
        (self.repo / "local.toml").write_text(
            "[overrides.ventoy]\nwindows = { asset = ['^ventoy-[\\d.]+-windows\\.zip$'], "
            "version = 'ventoy-([\\d.]+)-windows' }\n")
        self.cfg = cr.Config(repo=self.repo, windows=True)
        rc, out = self.fetch("ventoy")
        self.assertEqual(rc, 0, out)
        self.assertIn("sha256 from sha256.txt", out)
        entry = cr.load_lock(self.cfg)["ventoy"]
        self.assertEqual((entry["version"], entry["final"]), ("1.1.17", "ventoy-1.1.17"))
        self.assertTrue((self.cfg.cache / "ventoy/ventoy-1.1.17/Ventoy2Disk.exe").exists())
        self.assertEqual(self.run_quiet(cr.cmd_ventoy_path, self.cfg, None)[0], 0)
        # …and Linux, with the same manifest, still takes the tarball
        linux = cr.Config(repo=self.repo, windows=False)
        self.assertEqual(cr.resolve(next(t for t in linux.tools if t["name"] == "ventoy"), linux)["file"],
                         "ventoy-1.1.17-linux.tar.gz")

    def test_assets_folder_is_separate_from_your_folder(self):
        assets = self.tmp / "bundle"
        (assets / "pe/launcher").mkdir(parents=True)
        shutil.copy2(self.repo / "tools.toml", assets / "tools.toml")
        (assets / "pe/launcher/HelixApps.cmd").write_text("rem bundled")
        mine = self.tmp / "mine"
        mine.mkdir()
        (mine / "local.toml").write_text('[overrides.systemrescue]\ntitle = "My SR"\n')
        cfg = cr.Config(repo=mine, assets=assets)
        self.assertEqual(next(t for t in cfg.tools if t["name"] == "systemrescue")["title"], "My SR")
        self.cfg = cfg
        self.fetch("systemrescue")
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual((self.stick / "Apps/HelixApps.cmd").read_text(), "rem bundled")

    def test_dry_run_writes_nothing(self):
        self.fetch("systemrescue")
        rc, out = self.sync(dry_run=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(list(self.stick.iterdir()), [])


class TestPack(Base):
    def pack(self, out=None):
        out = out or self.tmp / "pack.zip"
        rc, log = self.run_quiet(cr.cmd_pack, self.cfg, type("A", (), {"output": str(out)})())
        self.assertEqual(rc, 0, log)
        return out, log

    def unpack(self, pack, target=None, **kw):
        args = dict(pack=str(pack), target=str(target or self.stick), init=True, dry_run=False,
                    verify=True, no_prune=False)
        args.update(kw)
        return self.run_quiet(cr.cmd_unpack, self.cfg, type("A", (), args)())

    def tree(self, root: Path) -> dict:
        skip = {cr.TAG_FILE, f"{cr.STATE_DIR}/state.json"}
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
                if p.is_file() and p.relative_to(root).as_posix() not in skip}

    def test_unpack_gives_the_same_stick_as_sync(self):
        self.assertEqual(self.fetch()[0], 0)
        (self.repo / "byo").mkdir()
        (self.repo / "byo/mine.iso").write_bytes(b"licensed iso")
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "mine"\ntitle = "Mine"\nkind = "iso"\ncategory = "rescue"\n'
            'source = "local"\nbyo = true\npath = "byo/mine.iso"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.fetch("mine")
        self.assertEqual(self.sync()[0], 0)
        pack, _ = self.pack()
        other = self.tmp / "stick2"
        other.mkdir()
        rc, out = self.unpack(pack, other)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.tree(other), self.tree(self.stick))
        self.assertIn(b"licensed iso", self.tree(other)["ISO/2-Rescue/mine.iso"])
        state = json.loads((other / cr.STATE_DIR / "state.json").read_text())
        self.assertIn("ISO/2-Rescue/mine.iso", state["files"])
        self.assertEqual(state["apps"], {"sysinternals": cr.load_lock(self.cfg)["sysinternals"]["version"]})
        # a second run copies nothing, and a later sync (refresh.sh) sees the stick as its own
        rc, out = self.unpack(pack, other)
        self.assertNotIn("copied", out)
        rc, out = self.run_quiet(cr.cmd_sync, self.cfg, type("A", (), dict(
            target=str(other), init=False, dry_run=False, verify=False, no_prune=False))())
        self.assertEqual(rc, 0, out)
        self.assertNotIn("copied", out)
        self.assertNotIn("backed up", out)

    def test_packs_from_before_the_rename_still_unpack(self):
        self.fetch()
        pack, _ = self.pack()
        old = self.tmp / "old.zip"
        with zipfile.ZipFile(pack) as src, zipfile.ZipFile(old, "w") as dst:
            for item in src.infolist():
                name = cr.OLD_PACK_META if item.filename == cr.PACK_META else item.filename
                dst.writestr(name, src.read(item.filename))
        rc, out = self.unpack(old)
        self.assertEqual(rc, 0, out)
        self.assertTrue((self.stick / "ISO/5-Diagnostics/memtest.iso").exists())

    def test_a_stick_from_before_the_rename_keeps_its_state(self):
        self.fetch()
        self.assertEqual(self.sync()[0], 0)
        (self.stick / cr.STATE_DIR).rename(self.stick / cr.OLD_STATE_DIR)     # as an older version left it
        rc, out = self.sync(init=False)
        self.assertEqual(rc, 0, out)
        self.assertTrue((self.stick / cr.STATE_DIR / "state.json").exists())
        self.assertFalse((self.stick / cr.OLD_STATE_DIR).exists())
        self.assertIn("already on stick", out)                               # nothing copied again

    def test_the_old_cache_moves_to_the_new_name(self):
        home = self.tmp / "home"
        (home / ".cache/commander-rescue/ventoy").mkdir(parents=True)
        (home / ".cache/commander-rescue/lock.json").write_text("{}")
        (self.repo / "tools.toml").write_text((self.repo / "tools.toml").read_text().replace(
            f'cache_dir = "{self.tmp / "cache"}"', 'cache_dir = "~/.cache/helix-boot"'))
        with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}):
            os.environ.pop("HELIX_CACHE", None)
            cfg = cr.Config(repo=self.repo)
        self.assertEqual(cfg.cache, home / ".cache/helix-boot")
        self.assertTrue((home / ".cache/helix-boot/lock.json").exists())
        self.assertFalse((home / ".cache/commander-rescue").exists())

    def test_nothing_fetched(self):
        with self.assertRaisesRegex(cr.RescueError, "nothing to pack"):
            self.run_quiet(cr.cmd_pack, self.cfg, type("A", (), {"output": str(self.tmp / "p.zip")})())
        self.assertFalse((self.tmp / "p.zip").exists())

    def test_damaged_iso_in_pack_is_refused(self):
        self.fetch()
        pack, _ = self.pack()
        with zipfile.ZipFile(pack) as zf:
            meta = json.loads(zf.read(cr.PACK_META))
            items = [(i, zf.read(i)) for i in zf.namelist()]
        meta["isos"][0]["sha256"] = "0" * 64
        bad = self.tmp / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            for name, data in items:
                zf.writestr(name, json.dumps(meta) if name == cr.PACK_META else data)
        with self.assertRaisesRegex(cr.RescueError, "damaged"):
            self.unpack(bad)
        self.assertEqual(list(self.stick.rglob("*.iso")), [])

    def test_not_a_pack(self):
        z = self.tmp / "x.zip"
        z.write_bytes(zipped({"hello.txt": b"hi"}))
        with self.assertRaisesRegex(cr.RescueError, "not a Helix Boot pack"):
            self.unpack(z)

    def test_unpack_prunes_what_the_pack_dropped(self):
        self.fetch()
        self.assertEqual(self.sync()[0], 0)
        old = self.stick / "ISO/2-Rescue/systemrescue-12.02-amd64.iso"
        self.assertTrue(old.exists())
        (self.repo / "local.toml").write_text('[overrides.systemrescue]\nenabled = false\n')
        self.cfg = cr.Config(repo=self.repo)
        pack, _ = self.pack()
        rc, out = self.unpack(pack)
        self.assertEqual(rc, 0, out)
        self.assertFalse(old.exists())
        self.assertTrue((self.stick / "ISO/5-Diagnostics/memtest.iso").exists())

    def test_ventoy_comes_out_of_the_pack_offline(self):
        self.fetch()
        pack, _ = self.pack()
        shutil.rmtree(WEB)          # no network from here on
        WEB.mkdir()
        rc, out = self.run_quiet(cr.cmd_ventoy_path, self.cfg, type("A", (), {"from_pack": str(pack)})())
        self.assertEqual(rc, 0, out)
        v = Path(out.strip())
        self.assertEqual(v.name, "ventoy-1.1.17")
        self.assertTrue(os.access(v / "Ventoy2Disk.sh", os.X_OK))
        rc, again = self.run_quiet(cr.cmd_ventoy_path, self.cfg, type("A", (), {"from_pack": str(pack)})())
        self.assertEqual(again, out)

    def test_file_tools_and_bios_labels(self):
        put("wim/ventoy_wimboot.img", b"wimboot plugin")
        (self.repo / "byo").mkdir()
        (self.repo / "byo/old.iso").write_bytes(fake_iso([0]))
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "wimboot"\ntitle = "wimboot"\nkind = "file"\ndest = "ventoy/ventoy_wimboot.img"\n'
            f'source = "url"\nurl = "{BASE}/wim/ventoy_wimboot.img"\n'
            f'checksum = [{{ sha256 = "{sha(b"wimboot plugin")}" }}]\n'
            '[[tool]]\nname = "old"\ntitle = "Old DOS Tool"\nkind = "iso"\ncategory = "rescue"\n'
            'source = "local"\nbyo = true\npath = "byo/old.iso"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.assertEqual(self.fetch()[0], 0)
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual((self.stick / "ventoy/ventoy_wimboot.img").read_bytes(), b"wimboot plugin")
        menu = json.loads((self.stick / "ventoy/ventoy.json").read_text())
        self.assertIn("Old DOS Tool  [BIOS]", [a["alias"] for a in menu["menu_alias"]])
        self.assertFalse(any("[BIOS]" in a["alias"] for a in menu["menu_alias"] if "systemrescue" in a.get("image", "")))
        pack, _ = self.pack()                                     # and through a pack
        other = self.tmp / "stick2"
        other.mkdir()
        self.assertEqual(self.unpack(pack, other)[0], 0)
        self.assertEqual((other / "ventoy/ventoy_wimboot.img").read_bytes(), b"wimboot plugin")

    @unittest.skipUnless(shutil.which("7z") or shutil.which("7za") or shutil.which("7zz"), "needs 7-Zip")
    def test_tree_goes_on_once_and_is_then_left_alone(self):
        setup = zipped({"Start.exe": b"MZ start", "PortableApps/PortableApps.com/PortableAppsPlatform.exe": b"MZ pa",
                        "$PLUGINSDIR/junk.dll": b"x"})
        put("pa/download.html", f'<a href="{BASE}/pa/files/Platform_Setup_2.0.paf.exe">get it</a>'
                                f'<p>SHA256 Hash <b>:</b> {sha(setup)}</p>')
        put("pa/files/Platform_Setup_2.0.paf.exe", setup)
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "pa"\ntitle = "Platform"\nkind = "tree"\ndest = ""\n'
            'once = "PortableApps/PortableApps.com/PortableAppsPlatform.exe"\ndrop = [\'^\\$PLUGINSDIR(/|$)\']\n'
            f'source = "page"\npage = "{BASE}/pa/download.html"\nuser_agent = "browser"\n'
            "asset = ['Platform_Setup_[\\d.]+\\.paf\\.exe$']\nversion = 'Setup_([\\d.]+)\\.paf'\n"
            f'checksum = [{{ url = "{BASE}/pa/download.html", regex = \'SHA256 Hash ?: ?([0-9a-f]{{64}})\' }}]\n')
        self.cfg = cr.Config(repo=self.repo)
        rc, out = self.fetch()
        self.assertEqual(rc, 0, out)
        self.assertIn("Platform 2.0 — sha256 from", out)
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual((self.stick / "Start.exe").read_bytes(), b"MZ start")
        self.assertFalse((self.stick / "$PLUGINSDIR").exists())
        # The Platform updates itself and you install apps into it: sync must leave all that be
        (self.stick / "Start.exe").write_bytes(b"MZ newer, self-updated")
        (self.stick / "PortableApps/FirefoxPortable").mkdir(parents=True)
        (self.stick / "PortableApps/FirefoxPortable/FirefoxPortable.exe").write_bytes(b"MZ ff")
        rc, out = self.sync()
        self.assertIn("already on stick (it updates itself)", out)
        self.assertEqual((self.stick / "Start.exe").read_bytes(), b"MZ newer, self-updated")
        self.assertTrue((self.stick / "PortableApps/FirefoxPortable/FirefoxPortable.exe").exists())
        pack, _ = self.pack()                                   # same rules through a pack
        other = self.tmp / "stick2"
        other.mkdir()
        self.assertEqual(self.unpack(pack, other)[0], 0)
        self.assertEqual((other / "PortableApps/PortableApps.com/PortableAppsPlatform.exe").read_bytes(), b"MZ pa")
        rc, out = self.unpack(pack)
        self.assertIn("already on stick (it updates itself)", out)
        self.assertEqual((self.stick / "Start.exe").read_bytes(), b"MZ newer, self-updated")

    def test_page_hash_must_name_the_file(self):
        put("pa/download.html", f'<a href="{BASE}/pa/files/Other_1.0.paf.exe">x</a><p>SHA256 Hash: {"0" * 64}</p>')
        tool = {"name": "pa", "title": "Pa", "checksum": [{"url": f"{BASE}/pa/download.html", "regex": "SHA256 Hash ?: ?([0-9a-f]{64})"}]}
        with self.assertRaisesRegex(cr.RescueError, "couldn't find an upstream checksum"):
            cr.expected_hash(tool, {"file": "Platform_Setup_2.0.paf.exe"})

    def test_file_tool_can_be_a_local_folder(self):
        themes = self.repo / "byo/pa-themes"
        (themes / "Helix Teal").mkdir(parents=True)
        (themes / "Helix Teal/PATheme.ini").write_text("[ThemeDetails]\nName=Helix Teal\n")
        (themes / "Helix Teal/chrome.png").write_bytes(b"png")
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "pa-themes"\ntitle = "Themes"\nkind = "file"\n'
            'dest = "PortableApps/PortableApps.com/App/Graphics/Themes"\nsource = "local"\nbyo = true\n'
            'path = "byo/pa-themes"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.assertEqual(self.fetch()[0], 0)
        self.assertEqual(self.sync()[0], 0)
        dest = self.stick / "PortableApps/PortableApps.com/App/Graphics/Themes/Helix Teal"
        self.assertEqual((dest / "chrome.png").read_bytes(), b"png")
        (themes / "Helix Teal/chrome.png").write_bytes(b"png v2")       # edited: fetch sees it, sync copies it
        rc, out = self.fetch("pa-themes")
        self.assertIn("registered", out)
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual((dest / "chrome.png").read_bytes(), b"png v2")
        pack, _ = self.pack()
        other = self.tmp / "stick2"
        other.mkdir()
        self.assertEqual(self.unpack(pack, other)[0], 0)
        self.assertEqual((other / "PortableApps/PortableApps.com/App/Graphics/Themes/Helix Teal/PATheme.ini")
                         .read_text(), "[ThemeDetails]\nName=Helix Teal\n")

    def test_ventoy_mode_goes_into_the_file_name(self):
        self.fetch()
        self.assertEqual(self.sync()[0], 0)
        (self.repo / "local.toml").write_text('[overrides.systemrescue]\nventoy_mode = "wimboot"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.assertEqual(self.sync()[0], 0)
        rescue = self.stick / "ISO/2-Rescue"
        self.assertEqual(sorted(f.name for f in rescue.iterdir()), ["systemrescue-12.02-amd64_VTWIMBOOT.iso"])
        menu = json.loads((self.stick / "ventoy/ventoy.json").read_text())
        self.assertIn({"image": "/ISO/2-Rescue/systemrescue-12.02-amd64_VTWIMBOOT.iso", "alias": "SystemRescue"},
                      menu["menu_alias"])
        (self.repo / "local.toml").write_text('[overrides.systemrescue]\nventoy_mode = "fast"\n')
        with self.assertRaisesRegex(cr.RescueError, "ventoy_mode must be one of"):
            cr.Config(repo=self.repo)

    def test_local_tree_seeds_settings_once(self):
        seed = self.repo / "seed"
        seed.mkdir()
        (seed / "Menu.ini").write_text("Theme=RetroDark\n")
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "seed"\ntitle = "Starting settings"\nkind = "tree"\ndest = "PA/Data"\n'
            'once = "Menu.ini"\nsource = "local"\npath = "seed"\n')
        self.cfg = cr.Config(repo=self.repo)
        self.assertEqual(self.fetch()[0], 0)
        self.assertEqual(self.sync()[0], 0)
        ini = self.stick / "PA/Data/Menu.ini"
        self.assertEqual(ini.read_text(), "Theme=RetroDark\n")
        ini.write_text("Theme=Smooth\n")                     # the user picks another theme later
        rc, out = self.sync()
        self.assertIn("already on stick (it updates itself)", out)
        self.assertEqual(ini.read_text(), "Theme=Smooth\n")

    def test_shipped_portableapps_themes(self):
        cfg = cr.Config(repo=ROOT, manifest=ROOT / "tools.toml")
        themes = next(t for t in cfg.tools if t["name"] == "portableapps-themes")
        for slot in (ROOT / themes["path"]).iterdir():
            self.assertIn(slot.name, ("Modern", "ModernDark", "Retro", "RetroDark", "Smooth", "SmoothDark"))
            for f in ("chrome.png", "preview.png", "drive_space_slider.png", "PATheme.ini"):
                self.assertTrue((slot / f).is_file(), f"{slot.name}/{f}")
        ini = (ROOT / "portableapps/settings/PortableAppsMenu.ini").read_bytes()
        self.assertTrue(ini.startswith(b"\xff\xfe"), "the Platform's settings file is UTF-16 LE")
        self.assertIn("Theme=RetroDark", ini.decode("utf-16"))

    def test_file_tool_needs_a_safe_dest(self):
        (self.repo / "local.toml").write_text(
            '[[tool]]\nname = "bad"\ntitle = "Bad"\nkind = "file"\ndest = "../etc/x"\nsource = "local"\npath = "x"\n')
        with self.assertRaisesRegex(cr.RescueError, "needs 'dest'"):
            cr.Config(repo=self.repo)

    def test_the_zip_is_all_another_pc_needs(self):
        self.fetch()
        pack, _ = self.pack(self.tmp / "away" / "helix-boot-2026-01-01.zip")
        away = pack.parent
        with zipfile.ZipFile(pack) as zf:  # like `unzip pack.zip 'installer/*'`: files and their modes
            for m in zf.infolist():
                if m.filename.startswith("installer/") and not m.is_dir():
                    zf.extract(m, away)
                    os.chmod(away / m.filename, (m.external_attr >> 16) & 0o777 or 0o644)
        inst = away / "installer"
        for f in ("helix", "install.sh", "refresh.sh", "theme.sh"):
            self.assertTrue(os.access(inst / f, os.X_OK), f)
        self.assertIn(pack.name, (inst / "README.txt").read_text())
        found = subprocess.run(["bash", "-c", f'source "{inst}/scripts/common.sh"; bundled_pack "{inst}"'],
                               capture_output=True, text=True)
        self.assertEqual(found.returncode, 0, found.stderr)
        self.assertEqual(found.stdout.strip(), str(pack))
        # outside a pack's installer folder nothing is picked up
        none = subprocess.run(["bash", "-c", f'source "{ROOT}/scripts/common.sh"; bundled_pack "{ROOT}"'],
                              capture_output=True, text=True)
        self.assertEqual((none.returncode, none.stdout), (0, ""))
        # the bundled helix fills a stick on its own
        env = {**os.environ, "HELIX_CACHE": str(self.tmp / "away-cache"), "NO_COLOR": "1"}
        run = subprocess.run([str(inst / "helix"), "unpack", str(pack), str(self.stick), "--init"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue((self.stick / "ISO/5-Diagnostics/memtest.iso").exists())
        self.assertTrue((self.stick / "Apps/sysinternals/procexp64.exe").exists())

    def windows_ventoy_upstream(self, app: bytes | None = b"MZ helix boot", app_digest: str | None = None):
        self.wzip = zipped({"ventoy-1.1.17/Ventoy2Disk.exe": b"MZ ventoy"})
        gh_release("ventoy/Ventoy", "v1.1.17", {
            "ventoy-1.1.17-linux.tar.gz": self.ventoy_tgz,
            "ventoy-1.1.17-windows.zip": self.wzip,
            "sha256.txt": (f"{sha(self.ventoy_tgz)}  ventoy-1.1.17-linux.tar.gz\n"
                           f"{sha(self.wzip)}  ventoy-1.1.17-windows.zip\n").encode(),
        }, digests=False)
        if app is not None:
            gh_release(cr.APP_REPO, "v0.5.0", {cr.APP_EXE: app})
            if app_digest:   # a release whose published digest doesn't match the file
                rel = json.loads((WEB / f"gh/repos/{cr.APP_REPO}/releases/latest").read_text())
                rel["assets"][0]["digest"] = "sha256:" + app_digest
                put(f"gh/repos/{cr.APP_REPO}/releases/latest", json.dumps(rel))
        toml = self.repo / "tools.toml"
        line = "version = 'ventoy-([\\d.]+)-linux'\n"
        self.assertIn(line, toml.read_text())
        toml.write_text(toml.read_text().replace(line, line + "windows = { asset = ['^ventoy-[\\d.]+-windows\\.zip$'], "
                                                               "version = 'ventoy-([\\d.]+)-windows' }\n"))
        self.cfg = cr.Config(repo=self.repo)

    def test_pack_sets_up_sticks_from_windows_too(self):
        self.windows_ventoy_upstream()
        self.fetch()
        pack, log = self.pack()
        with zipfile.ZipFile(pack) as zf:
            meta = json.loads(zf.read(cr.PACK_META))
            self.assertEqual(zf.read("installer/ventoy-1.1.17-windows.zip"), self.wzip)
            self.assertEqual(zf.read(f"installer/{cr.APP_EXE}"), b"MZ helix boot")
            self.assertIn("HelixBoot.exe", zf.read("installer/README.txt").decode())
        self.assertEqual(meta["ventoy_windows"], {"file": "installer/ventoy-1.1.17-windows.zip", "version": "1.1.17"})
        self.assertEqual(meta["app"]["version"], "0.5.0")
        self.assertIn(f"On Windows: put installer\\{cr.APP_EXE} beside the pack", log)

        shutil.rmtree(WEB)          # offline from here: each system gets its own Ventoy out of the pack
        WEB.mkdir()
        win = cr._ventoy_from_pack(self.cfg, str(pack), windows=True)
        self.assertEqual((win / "Ventoy2Disk.exe").read_bytes(), b"MZ ventoy")
        lin = cr._ventoy_from_pack(self.cfg, str(pack), windows=False)
        self.assertTrue(os.access(lin / "Ventoy2Disk.sh", os.X_OK))
        self.assertEqual(cr._ventoy_from_pack(self.cfg, str(pack), windows=True), win)   # unpacked once

        # A pack made while offline still carries what's in the cache
        again, log = self.pack(self.tmp / "offline.zip")
        self.assertIn("couldn't check for a newer one", log)
        with zipfile.ZipFile(again) as zf:
            self.assertIn("installer/ventoy-1.1.17-windows.zip", zf.namelist())
            self.assertIn(f"installer/{cr.APP_EXE}", zf.namelist())

    def test_linux_only_pack_says_so_on_windows(self):
        self.fetch()
        pack, log = self.pack()
        self.assertIn(f"no released {cr.APP_EXE} to include", log)
        with self.assertRaisesRegex(cr.RescueError, "Ventoy for Linux only"):
            cr._ventoy_from_pack(self.cfg, str(pack), windows=True)

    def test_app_with_a_bad_checksum_stays_out_of_the_pack(self):
        self.windows_ventoy_upstream(app_digest="0" * 64)
        self.fetch()
        pack, log = self.pack()
        self.assertIn("checksum MISMATCH", log)
        with zipfile.ZipFile(pack) as zf:
            self.assertNotIn(f"installer/{cr.APP_EXE}", zf.namelist())
            self.assertIsNone(json.loads(zf.read(cr.PACK_META))["app"])

    def tamper(self, pack: Path, meta: dict | None = None, add: dict | None = None) -> Path:
        """A copy of pack with its metadata changed and members added, as an attacker would."""
        out = pack.with_name(f"tampered-{len(list(pack.parent.glob('tampered-*.zip')))}.zip")
        with zipfile.ZipFile(pack) as src, zipfile.ZipFile(out, "w") as dst:
            for m in src.infolist():
                data = src.read(m)
                if m.filename == cr.PACK_META and meta:
                    data = json.dumps({**json.loads(data), **meta}).encode()
                dst.writestr(m, data)
            for name, data in (add or {}).items():
                dst.writestr(name, data)
        return out

    def test_pack_paths_cannot_leave_the_stick(self):
        self.fetch()
        pack, _ = self.pack()
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "sysinternals").mkdir()
        (outside / "sysinternals" / "keep.txt").write_text("mine")
        for how, bad in [
            ("absolute apps_root (F1)", self.tamper(pack, meta={"apps_root": str(outside)})),
            ("apps_root climbing out (F1)", self.tamper(pack, meta={"apps_root": "../outside"})),
            ("Windows drive apps_root (F1)", self.tamper(pack, meta={"apps_root": "C:/Windows"})),
            ("absolute iso_root", self.tamper(pack, meta={"iso_root": str(outside)})),
            ("app member with an absolute rest (F2)",
             self.tamper(pack, add={f"stick/Apps/sysinternals/{outside}/evil.txt": b"x"})),
            ("extra with an absolute rest (F3)", self.tamper(pack, add={f"stick/{outside}/evil.txt": b"x"})),
            ("drive-qualified member", self.tamper(pack, add={"stick/C:/evil.txt": b"x"})),
            ("app name that's a path", self.tamper(pack, meta={"apps": {"../outside": "1"}})),
        ]:
            with self.subTest(how):
                shutil.rmtree(self.stick)
                self.stick.mkdir()
                with self.assertRaisesRegex(cr.RescueError, "refusing unsafe|refusing .* outside"):
                    self.unpack(bad)
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ["sysinternals"], how)
                self.assertEqual((outside / "sysinternals" / "keep.txt").read_text(), "mine", how)

    def test_stick_state_cannot_delete_outside_the_stick(self):
        # F7/F8: .helix-boot/state.json is on the stick, which gets plugged into infected PCs
        self.fetch()
        victim = self.tmp / "victim"
        victim.mkdir()
        (victim / "precious.txt").write_text("mine")
        pack, _ = self.pack()
        for how, run in [("sync (F7)", lambda: self.sync(init=False)), ("unpack (F8)", lambda: self.unpack(pack, init=False))]:
            with self.subTest(how):
                self.assertEqual(self.sync()[0], 0)
                state_file = self.stick / cr.STATE_DIR / "state.json"
                state = json.loads(state_file.read_text())
                state["apps"].update({str(victim): "1", "../../victim": "1", "..": "1"})
                state_file.write_text(json.dumps(state))
                rc, out = run()
                self.assertEqual(rc, 0, out)
                self.assertIn("ignoring an app name", out)
                self.assertEqual((victim / "precious.txt").read_text(), "mine")
                self.assertNotIn(str(victim), json.loads(state_file.read_text())["apps"])

    def test_pack_without_ventoy(self):
        self.fetch("systemrescue")
        pack, log = self.pack()
        self.assertIn("can refresh a stick but not set up a new one", log)
        with self.assertRaisesRegex(cr.RescueError, "no Ventoy installer"):
            self.run_quiet(cr.cmd_ventoy_path, self.cfg, type("A", (), {"from_pack": str(pack)})())


def fake_iso(platforms: list[int], efi_file: bool = False) -> bytes:
    """A minimal ISO: an El Torito catalog listing `platforms` (0 = BIOS, 0xEF = UEFI) and,
    optionally, EFI/BOOT/BOOTX64.EFI in the ISO 9660 tree."""
    S = 2048
    img = bytearray(S * 30)

    def rec(name: bytes, lba: int, size: int, is_dir: bool) -> bytes:
        r = bytearray(33 + len(name) + (len(name) + 1) % 2)
        r[0] = len(r)
        r[2:6], r[10:14] = lba.to_bytes(4, "little"), size.to_bytes(4, "little")
        r[25], r[32] = 2 if is_dir else 0, len(name)
        r[33:33 + len(name)] = name
        return bytes(r)

    pvd = bytearray(S)
    pvd[0], pvd[1:6] = 1, b"CD001"
    pvd[156:156 + 34] = rec(b"\0", 20, S, True)
    img[16 * S:17 * S] = pvd
    img[20 * S:21 * S] = (rec(b"\0", 20, S, True) + rec(b"\1", 20, S, True) + rec(b"EFI", 21, S, True)).ljust(S, b"\0")
    img[21 * S:22 * S] = rec(b"BOOT", 22, S, True).ljust(S, b"\0")
    if efi_file:
        img[22 * S:23 * S] = rec(b"BOOTX64.EFI;1", 23, 10, False).ljust(S, b"\0")
    brvd = bytearray(S)
    brvd[1:6], brvd[6], brvd[7:30] = b"CD001", 1, b"EL TORITO SPECIFICATION"
    brvd[0x47:0x4B] = (25).to_bytes(4, "little")
    img[17 * S:18 * S] = brvd
    cat = bytearray(S)
    cat[0], cat[1] = 1, platforms[0] if platforms else 0
    cat[32] = 0x88 if platforms else 0
    for n, plat in enumerate(platforms[1:]):
        i = 64 + n * 64
        cat[i], cat[i + 1], cat[i + 2] = 0x91 if n == len(platforms) - 2 else 0x90, plat, 1
        cat[i + 32] = 0x88
    img[25 * S:26 * S] = cat
    return bytes(img)


class TestPortableAppsLogo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="helix-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def png(width, height, noise=True):
        import struct, zlib
        rows = b"".join(b"\0" + (os.urandom(width * 4) if noise else bytes(width * 4)) for _ in range(height))
        return (b"\x89PNG\r\n\x1a\n" + cr._png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                + cr._png_chunk(b"IDAT", zlib.compress(rows)) + cr._png_chunk(b"IEND", b""))

    def chunks(self, png):
        import struct, zlib
        i, out = 8, []
        while i < len(png):
            n, kind = struct.unpack(">I4s", png[i:i + 8])
            data = png[i + 8:i + 8 + n]
            self.assertEqual(struct.unpack(">I", png[i + 8 + n:i + 12 + n])[0], zlib.crc32(kind + data) & 0xFFFFFFFF)
            out.append((kind, data))
            i += 12 + n
        return out

    def exe_with(self, *parts):
        exe = self.tmp / "PortableAppsPlatform.exe"
        exe.write_bytes(b"MZ" + os.urandom(300) + b"".join(parts) + b"tail")
        return exe

    @staticmethod
    def image(name, png):
        return b"\x06TImage" + bytes([len(name)]) + name + b"\x04Left\x02\x00Picture.Data\n\x00\x00\x00\x00\tTPngImage" + png

    def test_both_logos_are_blanked_in_place(self):
        icon = self.image(b"imgEject", self.png(24, 17))              # other pictures stay as they are
        grey, white = self.png(300, 50), self.png(135, 75)
        exe = self.exe_with(icon, self.image(b"imgPortableAppsLogo", grey), self.image(b"imgPortableAppsLogo2", white))
        before = exe.read_bytes()
        self.assertEqual(cr._restyle_platform(exe, self.tmp / "Data/orig.exe"), "patched")
        after = exe.read_bytes()
        self.assertEqual(len(after), len(before))
        self.assertIn(self.png(24, 17)[:24], after)                  # the icon's header is untouched
        import struct, zlib
        for logo, size in ((grey, (300, 50)), (white, (135, 75))):
            start = before.index(logo)
            self.assertEqual(before[start - 20:start], after[start - 20:start])
            kinds = dict(self.chunks(after[start:start + len(logo)]))
            self.assertEqual(struct.unpack(">II", kinds[b"IHDR"][:8]), size)
            self.assertEqual(set(zlib.decompress(kinds[b"IDAT"])), {0})   # every pixel transparent
        self.assertEqual((self.tmp / "Data/orig.exe").read_bytes(), before)
        self.assertEqual(cr._restyle_platform(exe, self.tmp / "Data/orig.exe"), "already")

    def test_a_logo_restored_by_an_update_is_blanked_again(self):
        exe = self.exe_with(self.image(b"imgPortableAppsLogo", self.png(300, 50)),
                            self.image(b"imgPortableAppsLogo2", self.png(135, 75)))
        cr._restyle_platform(exe, self.tmp / "orig.exe")
        exe.write_bytes(exe.read_bytes() + self.image(b"imgPortableAppsLogo3", self.png(135, 75)))
        self.assertEqual(cr._restyle_platform(exe, self.tmp / "orig.exe"), "patched")
        self.assertEqual(cr._restyle_platform(exe, self.tmp / "orig.exe"), "already")

    @staticmethod
    def filtered_png(width, height, rgba):
        """A PNG whose rows use each of the five filter types in turn, as real encoders do."""
        import struct, zlib
        stride, rows, prev = width * 4, b"", bytes(width * 4)
        for y in range(height):
            line, ftype = rgba[y * stride:(y + 1) * stride], y % 5
            out = bytearray()
            for x in range(stride):
                a = line[x - 4] if x >= 4 else 0
                b, c = prev[x], prev[x - 4] if x >= 4 else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = (0, a, b, (a + b) // 2, a if pa <= pb and pa <= pc else b if pb <= pc else c)[ftype]
                out.append((line[x] - pred) & 255)
            rows += bytes([ftype]) + bytes(out)
            prev = line
        return (b"\x89PNG\r\n\x1a\n" + cr._png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                + cr._png_chunk(b"IDAT", zlib.compress(rows)) + cr._png_chunk(b"IEND", b"")
                + b"\0" * 400)[:-400] + b""

    def test_png_decoder_undoes_every_filter(self):
        pixels = os.urandom(16 * 16 * 4)
        self.assertEqual(cr._png_decode(self.filtered_png(16, 16, pixels)), (16, 16, bytearray(pixels)))

    def test_icons_are_recoloured_keeping_their_shape(self):
        pixels = bytearray(os.urandom(16 * 16 * 4))
        icon = self.filtered_png(16, 16, bytes(pixels))
        icon += b""                                               # real icons carry metadata; give it room
        icon = icon[:-12] + cr._png_chunk(b"tEXt", b"Software\0" + b"x" * 300) + icon[-12:]
        exe = self.exe_with(self.image(b"imgPortableAppsLogo", self.png(300, 50)),
                            self.image(b"imgLiveSearchIcon", icon))
        before = exe.read_bytes()
        result = cr._restyle_platform(exe, self.tmp / "orig.exe", {"imgLiveSearchIcon": "2AA9BE", "imgNope": "000000"})
        self.assertEqual(result, "patched (not found: imgNope)")
        after = exe.read_bytes()
        self.assertEqual(len(after), len(before))
        start = before.index(icon)
        w, h, px = cr._png_decode(after[start:start + len(icon)])
        self.assertEqual((w, h), (16, 16))
        self.assertEqual({bytes(px[i:i + 3]) for i in range(0, len(px), 4)}, {bytes.fromhex("2AA9BE")})
        self.assertEqual(px[3::4], pixels[3::4])                  # transparency unchanged: same shape
        self.assertEqual(cr._restyle_platform(exe, self.tmp / "orig.exe", {"imgLiveSearchIcon": "2AA9BE"}), "already")
        self.assertEqual((self.tmp / "orig.exe").read_bytes(), before)

    def test_unknown_layout_is_left_alone(self):
        exe = self.exe_with(self.image(b"imgEject", self.png(24, 17)))
        self.assertIn("not found", cr._restyle_platform(exe, self.tmp / "orig.exe"))
        self.assertFalse((self.tmp / "orig.exe").exists())


class TestBootModes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="helix-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def modes(self, data: bytes, name="x.iso"):
        (self.tmp / name).write_bytes(data)
        return cr._boot_modes(self.tmp / name)

    def test_modes(self):
        self.assertEqual(self.modes(fake_iso([0])), {"bios"})
        self.assertEqual(self.modes(fake_iso([0, 0xEF])), {"bios", "uefi"})
        self.assertEqual(self.modes(fake_iso([0xEF])), {"uefi"})
        self.assertEqual(self.modes(fake_iso([0], efi_file=True)), {"bios", "uefi"})  # EFI loader in the tree
        self.assertIsNone(self.modes(b"\0" * 40000))                                 # no El Torito: no guess
        self.assertIsNone(self.modes(fake_iso([0]), "x.wim"))                        # not an ISO


class TestProgress(unittest.TestCase):
    def test_whole_job_line(self):
        p = cr.Progress(total=4 << 30)
        p.start = 0.0
        p.file("(3/31) LazarusPE.iso", 3 << 30)
        p.tty = False                     # add() only counts; line() is what a terminal would see
        p.add(1 << 30)
        line = p.line(now=10.0)           # 1 GiB in 10 s
        self.assertIn("[=====>", line)
        self.assertIn(" 25%", line)
        self.assertIn("1.0 GiB/4.0 GiB", line)
        self.assertIn("102.4 MiB/s", line)
        self.assertIn("ETA 0m30s", line)
        self.assertIn("(3/31) LazarusPE.iso", line)

    def test_single_file_line(self):
        p = cr.Progress()
        p.tty = False
        p.file("(1/2) a.iso", 200)
        p.fstart = 0.0
        p.add(50)
        self.assertIn("a.iso  25%", p.line(now=1.0))

    def test_eta_format(self):
        self.assertEqual(cr._fmt_eta(75), "1m15s")
        self.assertEqual(cr._fmt_eta(3725), "1h02m")


class TestDownloadRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="helix-test-"))
        put("retry/tool.iso", b"iso bytes")
        Quiet.fail.clear()

    def tearDown(self):
        Quiet.fail.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self):
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            cr.download(f"{BASE}/retry/tool.iso", self.tmp / "tool.iso")

    def test_transient_500_is_retried(self):
        Quiet.fail["/retry/tool.iso"] = 2
        self.get()
        self.assertEqual((self.tmp / "tool.iso").read_bytes(), b"iso bytes")

    def test_gives_up_after_retries(self):
        Quiet.fail["/retry/tool.iso"] = len(cr.RETRY_DELAYS) + 1
        with self.assertRaisesRegex(cr.RescueError, "after 4 tries: HTTP 500"):
            self.get()

    def test_page_requests_are_retried_too(self):
        Quiet.fail["/retry/tool.iso"] = 2
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(cr.http_get(f"{BASE}/retry/tool.iso"), b"iso bytes")
        Quiet.fail["/retry/tool.iso"] = len(cr.RETRY_DELAYS) + 1
        with self.assertRaisesRegex(cr.RescueError, "HTTP 500"):
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                cr.http_get(f"{BASE}/retry/tool.iso")

    def test_404_is_not_retried(self):
        with self.assertRaisesRegex(cr.RescueError, "HTTP 404"):
            with redirect_stderr(io.StringIO()):
                cr.download(f"{BASE}/retry/missing.iso", self.tmp / "missing.iso")


class TestPortability(unittest.TestCase):
    def test_loads_without_a_console(self):
        # HelixBoot.exe started from Explorer: a windowed program has sys.stdout/stderr = None
        import importlib.machinery, importlib.util
        with unittest.mock.patch.object(sys, "stdout", None), unittest.mock.patch.object(sys, "stderr", None):
            loader = importlib.machinery.SourceFileLoader("helix_noconsole", str(ROOT / "helix"))
            mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("helix_noconsole", loader))
            loader.exec_module(mod)
            self.assertFalse(mod.C.on)
            self.assertFalse(mod.Progress(10).tty)

    def test_github_token_only_goes_to_github(self):
        # F6/F9: a scraped link to a look-alike host must not get the token
        with unittest.mock.patch.dict(os.environ, {"GITHUB_TOKEN": "secret"}), \
                unittest.mock.patch.object(cr, "GITHUB_API", "https://api.github.com"):
            def auth(url):
                req = cr._request(url)
                return req.unredirected_hdrs.get("Authorization"), req.headers.get("Authorization")
            self.assertEqual(auth("https://api.github.com/repos/a/b/releases/latest"), ("Bearer secret", None))
            for url in ("https://api.github.com.evil.example/x.zip", "https://api.github.comevil.example/x",
                        "http://api.github.com/repos/a/b", "https://evil.example/https://api.github.com/x",
                        "https://api.github.com:444/repos/a/b", "https://user@evil.example/api.github.com"):
                self.assertEqual(auth(url), (None, None), url)

    def test_powershell_with_non_ascii_text_has_a_bom(self):
        # Windows PowerShell 5.1 (Lazarus PE, the build VM) reads a .ps1 without a BOM as ANSI:
        # UTF-8 text turns into mojibake, and some of those bytes are quote characters to it.
        for f in ROOT.rglob("*.ps1"):
            data = f.read_bytes()
            if any(c > 0x7F for c in data):
                self.assertTrue(data.startswith(b"\xef\xbb\xbf"), f.relative_to(ROOT))

    def test_no_invalid_escape_sequences(self):
        # An escape like "\\H" in a normal string makes Python warn on every start (newer ones refuse it).
        import warnings
        for f in ("helix", "windows/helix_boot.py", "theme/build-theme.py", "portableapps/make-theme.py"):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                compile((ROOT / f).read_text(encoding="utf-8"), f, "exec")

    def test_flush_without_os_sync(self):
        # Windows has no os.sync(); sync used to crash there after copying everything.
        with unittest.mock.patch.object(cr.os, "sync", create=True) as s:
            cr._flush_volume(Path("/"))
            s.assert_called_once()
        saved = cr.os.sync
        del cr.os.sync
        try:
            cr._flush_volume(Path("/"))   # no os.sync, not Windows: quietly nothing
        finally:
            cr.os.sync = saved


class TestEncoding(unittest.TestCase):
    def test_text_io_is_always_utf8(self):
        # Windows defaults to cp1252: tools.toml's "→" would reach the boot menu as "â†’".
        import ast
        bad = []
        for node in ast.walk(ast.parse((ROOT / "helix").read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("read_text", "write_text") \
                    and not any(k.arg == "encoding" for k in node.keywords):
                bad.append(node.lineno)
        self.assertEqual(bad, [], "read_text/write_text without encoding= at these lines")


class TestShellHelpers(unittest.TestCase):
    def test_common_sh_does_not_shadow_commands(self):
        # scripts/common.sh once defined head(), which broke every `| head -n1`.
        names = subprocess.run(
            ["bash", "-c", f"source {ROOT / 'scripts/common.sh'}; compgen -A function"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        used = set()  # commands the shell scripts pipe into
        for f in ("install.sh", "refresh.sh", "theme.sh", "scripts/common.sh", "pe/vm/build-vm.sh", "pe/fix-bootmgr.sh"):
            used |= set(re.findall(r"(?<!\|)\|(?!\|)\s*([a-z][\w.-]*)", (ROOT / f).read_text()))
        self.assertIn("head", used)
        self.assertEqual(sorted(used & set(names)), [], "helper functions hide commands the scripts use")


if __name__ == "__main__":
    unittest.main()
