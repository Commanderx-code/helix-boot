"""End-to-end tests for crescue against a local fake GitHub / SourceForge / web server.

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
import unittest
import unittest.mock
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(tempfile.mkdtemp(prefix="crescue-web-"))


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

os.environ["CRESCUE_GITHUB_API"] = f"{BASE}/gh"
os.environ["CRESCUE_SF_RSS"] = BASE + "/sf/{project}/rss{path}/feed.xml"
os.environ["CRESCUE_SF_DL"] = BASE + "/dl/{project}{path}"
os.environ["NO_COLOR"] = "1"
os.environ.pop("GITHUB_TOKEN", None)

loader = importlib.machinery.SourceFileLoader("crescue", str(ROOT / "crescue"))
spec = importlib.util.spec_from_loader("crescue", loader)
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
name = "commander-pe"
title = "Commander PE"
kind = "iso"
category = "windows-pe"
source = "local"
path = "pe/out/CommanderPE.iso"

[[tool]]
name = "sysinternals"
title = "Sysinternals Suite"
kind = "app"
source = "url"
url = "{base}/web/SysinternalsSuite.zip"
entry = "procexp64.exe"
checksum = ["tofu"]
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="crescue-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.stick = self.tmp / "stick"
        self.stick.mkdir()
        (self.repo / "tools.toml").write_text(MANIFEST.format(cache=self.tmp / "cache", base=BASE))
        (self.repo / "pe/launcher").mkdir(parents=True)
        shutil.copy2(ROOT / "pe/launcher/CommanderApps.cmd", self.repo / "pe/launcher/")
        shutil.rmtree(WEB, ignore_errors=True)
        WEB.mkdir()
        # Upstream world, version 1
        self.ventoy_tgz = targz({"ventoy-1.1.17/Ventoy2Disk.sh": b"#!/bin/sh\necho ventoy\n"})
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
                         b"Sysinternals Suite|sysinternals\\procexp64.exe\r\n")
        self.assertTrue((self.stick / "Apps/CommanderApps.cmd").exists())
        vj = json.loads((self.stick / "ventoy/ventoy.json").read_text())
        aliases = {a.get("dir") or a.get("image"): a["alias"] for a in vj["menu_alias"]}
        self.assertEqual(aliases["/ISO/2-Rescue"], "Linux Rescue  →")
        tips = {t.get("dir") or t.get("image"): t["tip"] for t in vj["menu_tip"]["tips"]}
        self.assertEqual(tips["/ISO/2-Rescue"], "Linux rescue systems")
        self.assertIn("→", (self.stick / "ventoy/ventoy.json").read_text(encoding="utf-8"))  # not \u2192
        self.assertEqual(aliases["/ISO/2-Rescue/systemrescue-12.02-amd64.iso"], "SystemRescue  12.02")
        self.assertNotIn("/ISO/1-Windows-PE", aliases)             # empty category hidden
        self.assertTrue((self.stick / "commander-rescue.tag").exists())

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
        pe = self.repo / "pe/out/CommanderPE.iso"
        pe.parent.mkdir(parents=True)
        pe.write_bytes(b"winpe")
        rc, out = self.fetch("commander-pe")
        self.assertEqual(rc, 0, out)
        self.fetch("systemrescue")
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.stick / "ISO/1-Windows-PE/CommanderPE.iso").read_bytes(), b"winpe")

    def test_sync_refuses_non_ventoy_without_init(self):
        self.fetch("systemrescue")
        with self.assertRaisesRegex(cr.RescueError, "doesn't look like a Ventoy stick"):
            cr.cmd_sync(self.cfg, type("A", (), dict(target=str(self.stick), init=False, dry_run=False,
                                                     verify=False, no_prune=False))())

    def test_existing_ventoy_json_is_backed_up(self):
        self.fetch("systemrescue")
        (self.stick / "ventoy").mkdir()
        (self.stick / "ventoy/ventoy.json").write_text('{"mine": true}')
        rc, out = self.sync()
        self.assertEqual(rc, 0, out)
        backups = list((self.stick / "ventoy").glob("ventoy.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{"mine": true}')

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
        self.fetch("systemrescue", "memtest86plus", "commander-pe")
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
        (assets / "pe/launcher/CommanderApps.cmd").write_text("rem bundled")
        mine = self.tmp / "mine"
        mine.mkdir()
        (mine / "local.toml").write_text('[overrides.systemrescue]\ntitle = "My SR"\n')
        cfg = cr.Config(repo=mine, assets=assets)
        self.assertEqual(next(t for t in cfg.tools if t["name"] == "systemrescue")["title"], "My SR")
        self.cfg = cfg
        self.fetch("systemrescue")
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual((self.stick / "Apps/CommanderApps.cmd").read_text(), "rem bundled")

    def test_dry_run_writes_nothing(self):
        self.fetch("systemrescue")
        rc, out = self.sync(dry_run=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(list(self.stick.iterdir()), [])


class TestDownloadRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="crescue-test-"))
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
        for node in ast.walk(ast.parse((ROOT / "crescue").read_text(encoding="utf-8"))):
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
        for f in ("install.sh", "refresh.sh", "scripts/common.sh", "pe/vm/build-vm.sh"):
            used |= set(re.findall(r"(?<!\|)\|(?!\|)\s*([a-z][\w.-]*)", (ROOT / f).read_text()))
        self.assertIn("head", used)
        self.assertEqual(sorted(used & set(names)), [], "helper functions hide commands the scripts use")


if __name__ == "__main__":
    unittest.main()
