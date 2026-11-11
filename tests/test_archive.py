"""Runs archive.py against a local mock of the okdata API. No network, no real key."""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
os.environ["NO_PROXY"] = "*"

import archive  # noqa: E402
from mock_okdata import TEST_KEY, MockOkdata, error, ok  # noqa: E402

BOARD = [{"rank": 1, "name": "初雪|来了", "heat": 4821000, "url": "https://www.douyin.com/hot/1"},
         {"rank": 2, "name": "双十一", "heat": None, "url": None}]


def snapshot(fetched_at: str) -> dict:
    body = ok("douyin.trends.list", items=BOARD)
    body["meta"]["fetched_at"] = fetched_at
    return body


class ArchiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.answers = [snapshot("2026-11-11T15:30:00.000Z"), snapshot("2026-11-11T16:30:00.000Z")]
        self.api = MockOkdata({
            "/v1/douyin/trends/list": lambda q: (200, self.answers.pop(0)),
            "/v1/weibo/trends/list": lambda q: (503, error("upstream_busy", retry="no")),
        })
        archive.API = self.api.url
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.api.close()
        self.tmp.cleanup()

    def run_archive(self, *argv: str, key: str = TEST_KEY) -> tuple:
        os.environ["OKDATA_API_KEY"] = key
        err = io.StringIO()
        with redirect_stderr(err):
            code = archive.main(["--out", str(self.out), *argv])
        return code, err.getvalue()

    def test_snapshots_go_to_the_beijing_day(self) -> None:
        self.assertEqual(self.run_archive()[0], 0)
        self.assertEqual(self.run_archive()[0], 0)
        # 15:30 UTC is 23:30 on the 11th in Beijing; 16:30 UTC is 00:30 on the 12th.
        day11 = self.out / "douyin/2026/11/2026-11-11.csv"
        day12 = self.out / "douyin/2026/11/2026-11-12.csv"
        with day11.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r["name"] for r in rows], ["初雪|来了", "双十一"])
        self.assertTrue(day12.exists())
        latest = (self.out / "douyin/latest.md").read_text(encoding="utf-8")
        self.assertIn("[初雪\\|来了](https://www.douyin.com/hot/1)", latest)
        self.assertIn("| 2 | 双十一 |  |", latest)

    def test_same_day_appends_without_a_second_header(self) -> None:
        self.answers = [snapshot("2026-11-12T01:00:00.000Z"), snapshot("2026-11-12T05:00:00.000Z")]
        self.run_archive()
        self.run_archive()
        lines = (self.out / "douyin/2026/11/2026-11-12.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count(",".join(archive.FIELDS)), 1)
        self.assertEqual(len(lines), 5)

    def test_sends_key_and_idempotency_key(self) -> None:
        self.run_archive()
        headers = self.api.requests[0]["headers"]
        self.assertEqual(headers["authorization"], f"Bearer {TEST_KEY}")
        self.assertEqual(len(headers["idempotency-key"]), 36)

    def test_missing_key_points_to_sign_up(self) -> None:
        code, log = self.run_archive(key="")
        self.assertEqual(code, 2)
        self.assertIn("src=gh-douyin-hot-search-archive", log)
        self.assertEqual(self.api.requests, [])

    def test_errors_are_reported_and_nothing_is_written(self) -> None:
        code, log = self.run_archive("--board", "weibo")
        self.assertEqual(code, 1)
        self.assertIn("upstream_busy", log)
        self.assertFalse((self.out / "weibo").exists())


if __name__ == "__main__":
    unittest.main()
