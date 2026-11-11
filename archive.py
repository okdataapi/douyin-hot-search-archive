#!/usr/bin/env python3
"""抖音热搜每日存档：抓一次当前的抖音热搜榜，追加到按天分的 CSV，并更新 latest.md。

配合 GitHub Actions 每天定时跑，就是一份自己的热搜历史库。数据来自 okdata（https://okdata.online），
每次 $0.002。Python 3.9+，只用标准库。Key 放在环境变量 OKDATA_API_KEY。

    python3 archive.py                 # 抖音
    python3 archive.py --board weibo   # 也可以存微博、B站、小红书的榜

Archive the Douyin hot search board (or Weibo, Bilibili, Xiaohongshu) into daily CSV files.
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = "0.1.0"
SOURCE = "gh-douyin-hot-search-archive"
SIGN_UP = f"https://okdata.online/zh/signup/?src={SOURCE}"
API = os.environ.get("OKDATA_BASE_URL", "https://api.okdata.online").rstrip("/")
BEIJING = timezone(timedelta(hours=8))
BOARDS = {
    "douyin": ("douyin.trends.list", "抖音热搜"),
    "weibo": ("weibo.trends.list", "微博热搜"),
    "bilibili": ("bilibili.trends.list", "B站热门"),
    "xiaohongshu": ("xiaohongshu.trends.list", "小红书热点"),
}
FIELDS = ["fetched_at", "rank", "name", "heat", "url"]
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    def __init__(self, code: str, message: str, *, charged: Optional[bool] = False, retry: str = "no",
                 retry_after: Optional[float] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code, self.charged, self.retry, self.retry_after = code, charged, retry, retry_after


def fetch_board(endpoint: str, key: str, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """One paid call; retries reuse the Idempotency-Key so a retry is never charged twice."""
    headers = {"Authorization": f"Bearer {key}", "Idempotency-Key": str(uuid.uuid4()), "Accept": "application/json",
               "User-Agent": f"{SOURCE}/{VERSION}"}
    url = f"{API}/v1/{endpoint.replace('.', '/')}"
    return request_json(url, headers, sleep)


def _http_error(exc: HTTPError) -> ApiError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        body = None
    if isinstance(body, dict) and "code" in body:
        return ApiError(str(body["code"]), str(body.get("message")), charged=body.get("charged", False),
                        retry=str(body.get("retry", "no")), retry_after=body.get("retry_after_seconds"))
    return ApiError(f"http_{exc.code}", str(exc.reason), charged=None, retry="yes" if exc.code in RETRY_STATUSES else "no")


def request_json(url: str, headers: Dict[str, str], sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """GET with up to 2 retries on the same Idempotency-Key, so a retry is never charged twice. After a lost
    answer the call may still be running on the server: wait for it, and if we give up, say the charge is unknown."""
    retries, waits, ambiguous = 0, 0, False
    while True:
        try:
            with urlopen(Request(url, headers=headers), timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict) and body.get("code") == "ok":
                return body
            err = (ApiError(str(body.get("code")), str(body.get("message"))) if isinstance(body, dict)
                   else ApiError("bad_response", "unexpected answer", charged=None, retry="same_key"))
        except HTTPError as exc:
            err = _http_error(exc)
        except (OSError, ValueError, http.client.HTTPException) as exc:  # network, timeout, cut-off or non-JSON body
            err = ApiError("connection_error", str(exc), charged=None, retry="same_key")
        ambiguous = ambiguous or err.charged is None
        if ambiguous and err.code == "rate_limited" and waits < 5:
            waits += 1
            sleep(_wait(err.retry_after, 1.0))
            continue
        if err.retry not in ("yes", "same_key") or retries == 2:
            if ambiguous and err.charged is False:
                err.charged = None  # an earlier attempt may still finish and be billed
            raise err
        sleep(_wait(err.retry_after, 2.0 ** retries))
        retries += 1


def _wait(value: Any, default: float) -> float:
    """Seconds to sleep: the server's hint if it is a sane number, capped at 30."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(seconds, 0.0), 30.0)


def use_utf8() -> None:
    """Chinese text in and out, also on Windows consoles and pipes."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace" if stream is sys.stderr else "strict")


def cell(value: Any) -> Any:
    """Text that starts like a spreadsheet formula gets a leading ' so Excel shows it instead of running it."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def rows_of(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    fetched = (body.get("meta") or {}).get("fetched_at") or datetime.now(timezone.utc).isoformat()
    return [{"fetched_at": fetched, "rank": t.get("rank"), "name": t.get("name"), "heat": t.get("heat"), "url": t.get("url")}
            for t in body["data"]["items"]]


def day_file(root: Path, board: str, fetched_at: str) -> Path:
    """data/douyin/2026/11/2026-11-12.csv, by the Beijing date of the snapshot."""
    when = datetime.fromisoformat(fetched_at.replace("Z", "+00:00")).astimezone(BEIJING)
    return root / board / f"{when:%Y}" / f"{when:%m}" / f"{when:%Y-%m-%d}.csv"


def append_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)


def latest_md(board: str, rows: List[Dict[str, Any]]) -> str:
    title = BOARDS[board][1]
    when = rows[0]["fetched_at"] if rows else ""
    lines = [f"# {title}（最新一次存档）", "", f"抓取时间：{when}（UTC）。来源：{title}，经 okdata 获取。", "",
             "| 排名 | 话题 | 热度 |", "|---|---|---|"]
    for r in rows:
        name = str(r["name"]).replace("|", "\\|")
        cell = f"[{name}]({r['url']})" if r.get("url") else name
        lines.append(f"| {r['rank']} | {cell} | {r['heat'] if r['heat'] is not None else ''} |")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    use_utf8()
    p = argparse.ArgumentParser(description="把热搜榜存成按天分的 CSV（数据来自 okdata，每次 $0.002 起）。")
    p.add_argument("--board", choices=sorted(BOARDS), default="douyin", help="哪个榜，默认抖音")
    p.add_argument("--out", default="data", help="存到哪个目录，默认 data/")
    args = p.parse_args(argv)
    key = os.environ.get("OKDATA_API_KEY", "").strip()
    if not key:
        print(f"缺少 OKDATA_API_KEY。先在 {SIGN_UP} 注册拿 key。", file=sys.stderr)
        return 2
    endpoint, title = BOARDS[args.board]
    try:
        body = fetch_board(endpoint, key)
    except ApiError as err:
        charged = "不扣费" if err.charged is False else "是否扣费未知"
        print(f"{title}没取到：{err}（{charged}）", file=sys.stderr)
        return 1
    rows = rows_of(body)
    if not rows:
        print(f"{title}这次是空的，没有写文件。", file=sys.stderr)
        return 0
    root = Path(args.out)
    path = day_file(root, args.board, rows[0]["fetched_at"])
    append_csv(path, rows)
    (root / args.board / "latest.md").write_text(latest_md(args.board, rows), encoding="utf-8")
    cost = (body.get("meta") or {}).get("billing", {}).get("amount", "?")
    print(f"{title} {len(rows)} 条 → {path}（花费 ${cost}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
