"""Testes do downloader sem rede: `urlopen` é substituído por respostas falsas.

    python -m unittest discover tests
"""

import http.client
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import yaml

from blackspot import download

MANIFEST = """\
download:
  url_template: https://example.invalid/{drive_id}
files:
  - key: bat_2024_pessoa
    system: bat
    dataset: pessoa
    year: 2024
    drive_id: ID2024
    filename: acidentes2024.zip
    reference:
      sha256: "{sha}"
      size_bytes: 1
      drive_last_modified: "2024-01-01T00:00:00Z"
      verified_at: "2026-01-01"
  - key: bat_2025_pessoa
    system: bat
    dataset: pessoa
    year: 2025
    drive_id: ID2025
    filename: acidentes2025.zip
    reference:
      sha256: "{sha}"
      size_bytes: 1
      drive_last_modified: "2025-01-01T00:00:00Z"
      verified_at: "2026-01-01"
"""


def zip_bytes(content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dados.csv", content)
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"Content-Type": "application/zip",
                        "Last-Modified": "Tue, 22 Sep 2026 22:32:39 GMT"}


class DownloadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dest = self.root / "raw"
        self.manifest = self.root / "sources.yaml"
        self.body = zip_bytes("id;pesid\n1;1\n")
        self.sha = download.hashlib.sha256(self.body).hexdigest()
        self.manifest.write_text(MANIFEST.replace("{sha}", self.sha), encoding="utf-8")
        sleep = mock.patch.object(download.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def run_main(self, *args: str) -> int:
        return download.main(["--manifest", str(self.manifest), "--dest", str(self.dest), *args])

    def report(self) -> dict:
        return json.loads((self.dest / download.REPORT_NAME).read_text(encoding="utf-8"))

    def test_download_ok(self):
        with mock.patch.object(download.urllib.request, "urlopen",
                               side_effect=lambda *a, **k: FakeResponse(self.body)):
            self.assertEqual(self.run_main(), 0)
        self.assertEqual({r["status"] for r in self.report()["results"]}, {"downloaded"})

    def test_connection_cut_is_reported_not_raised(self):
        def urlopen(req, timeout):
            if "ID2024" in req.full_url:
                raise http.client.IncompleteRead(b"abc", 100)
            return FakeResponse(self.body)

        with mock.patch.object(download.urllib.request, "urlopen", side_effect=urlopen):
            self.assertEqual(self.run_main(), 1)
        status = {r["key"]: r["status"] for r in self.report()["results"]}
        self.assertEqual(status, {"bat_2024_pessoa": "error", "bat_2025_pessoa": "downloaded"})
        self.assertEqual(list(self.dest.glob("*.part")), [])

    def test_mismatch_warns_and_strict_exits_2(self):
        other = zip_bytes("id;pesid\n2;2\n")
        with mock.patch.object(download.urllib.request, "urlopen",
                               side_effect=lambda *a, **k: FakeResponse(other)):
            self.assertEqual(self.run_main(), 0)
            self.assertEqual(self.run_main("--strict"), 2)

    def test_accept_cached_file_clears_last_modified(self):
        self.dest.mkdir()
        (self.dest / "acidentes2024.zip").write_bytes(zip_bytes("revisado\n"))
        self.assertEqual(self.run_main("--accept-new-hash", "bat_2024_pessoa"), 0)

        entries = {e["key"]: e for e in yaml.safe_load(self.manifest.read_text())["files"]}
        ref = entries["bat_2024_pessoa"]["reference"]
        self.assertEqual(ref["sha256"], download.sha256_of(self.dest / "acidentes2024.zip"))
        self.assertIsNone(ref["drive_last_modified"])
        # A outra entrada fica intacta.
        self.assertEqual(entries["bat_2025_pessoa"]["reference"]["sha256"], self.sha)


class RealManifestTest(unittest.TestCase):
    def test_manifest_is_consistent(self):
        entries = download.load_manifest(download.DEFAULT_MANIFEST)["files"]
        self.assertEqual(len(entries), 50)
        for e in entries:
            with self.subTest(key=e["key"]):
                self.assertEqual(e["key"], f"{e['system']}_{e['year']}_{e['dataset']}")
                self.assertEqual(e["system"], "br_brasil" if e["year"] <= 2016 else "bat")
                self.assertRegex(str(e["reference"]["sha256"]), r"^[0-9a-f]{64}$")
        self.assertEqual(len({e["drive_id"] for e in entries}), 50)


if __name__ == "__main__":
    unittest.main()
