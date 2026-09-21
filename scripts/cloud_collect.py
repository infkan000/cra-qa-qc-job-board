#!/usr/bin/env python3
"""Collect CRA/QA/QC roles from public company career pages.

Uses public search results and public Workday endpoints only. No account
credentials are read or required.
"""

from __future__ import annotations

import email.utils
import html
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "data" / "config.json"
PUBLIC_DIR = ROOT / "public"
sys.path.insert(0, str(ROOT / "scripts"))
import manage_jobs  # noqa: E402

UA = "CRA-QA-QC-Job-Board/1.0 (public GitHub Actions job collector)"
CITY_RE = re.compile(r"广州|深圳|Guangzhou|Shenzhen|Canton", re.I)
ROLE_RE = re.compile(
    r"(?:\bCRA\b|clinical research associate|clinical monitor|临床监查(?:员)?|"
    r"\bQA\b|quality assurance|质量保证|质量体系|质量管理|GCP quality|GMP quality|"
    r"\bQC\b|quality control|质量控制|QC analyst|QC specialist)",
    re.I,
)


def request_text(url: str, *, payload: dict | None = None) -> str:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": UA, "Accept": "application/json, application/rss+xml, text/xml", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def plain(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_url(value: str) -> str:
    parts = urllib.parse.urlsplit(str(value or "").strip())
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def city_from(text: str) -> str:
    cities = []
    if re.search(r"广州|Guangzhou|Canton", text, re.I):
        cities.append("广州")
    if re.search(r"深圳|Shenzhen", text, re.I):
        cities.append("深圳")
    return " / ".join(cities)


def role_score(text: str) -> int:
    hits = {m.group(0).lower() for m in ROLE_RE.finditer(text)}
    return min(98, 72 + len(hits) * 6)


def rss_date(value: str) -> str:
    try:
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def collect_search_source(item: dict) -> list[dict]:
    domain = str(item["domain"]).lower()
    jobs = []
    seen = set()
    for city in ("Guangzhou", "Shenzhen"):
        query = f'site:{domain} (CRA OR "clinical research associate" OR "quality assurance" OR "quality control") {city}'
        rss_url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
        root = ET.fromstring(request_text(rss_url))
        for node in root.findall(".//item"):
            title = plain(node.findtext("title"))
            summary = plain(node.findtext("description"))
            url = clean_url(node.findtext("link"))
            host = (urllib.parse.urlsplit(url).hostname or "").lower()
            combined = f"{title} {summary}"
            if not (host == domain or host.endswith("." + domain)):
                continue
            if not CITY_RE.search(combined + " " + url) or not ROLE_RE.search(combined):
                continue
            if url in seen:
                continue
            seen.add(url)
            jobs.append({
                "title": title,
                "company": item["company"],
                "city": city_from(combined + " " + url),
                "salary": "未披露",
                "summary": summary[:680] + ("…" if len(summary) > 680 else ""),
                "source": item["source"],
                "url": url,
                "posted_date": rss_date(node.findtext("pubDate")),
                "is_foreign": True,
                "match_score": role_score(combined),
                "is_expired": False,
                "expired_reason": "",
            })
    return jobs


def collect_workday(source: dict) -> list[dict]:
    host = source["host"].rstrip("/")
    api = f"{host}/wday/cxs/{source['tenant']}/{source['site']}"
    public = source["public_base"].rstrip("/")
    found = {}
    for query in ("Guangzhou", "Shenzhen"):
        offset = 0
        while True:
            payload = json.loads(request_text(
                f"{api}/jobs",
                payload={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": query},
            ))
            page = payload.get("jobPostings") or []
            for listing in page:
                path = str(listing.get("externalPath") or "")
                if path:
                    found[path] = listing
            offset += len(page)
            if not page or offset >= int(payload.get("total") or 0):
                break

    jobs = []
    for path, listing in found.items():
        detail = json.loads(request_text(f"{api}{path}"))
        info = detail.get("jobPostingInfo") or {}
        title = plain(info.get("title") or listing.get("title"))
        description = plain(info.get("jobDescription"))
        location = plain(info.get("location") or listing.get("locationsText"))
        combined = f"{title} {location} {description} {path}"
        if not CITY_RE.search(combined) or not ROLE_RE.search(combined):
            continue
        jobs.append({
            "title": title,
            "company": source["company"],
            "city": city_from(combined),
            "salary": "未披露",
            "summary": description[:680] + ("…" if len(description) > 680 else ""),
            "source": source["source"],
            "url": clean_url(public + path),
            "posted_date": str(info.get("startDate") or "")[:10],
            "is_foreign": True,
            "match_score": role_score(combined),
            "is_expired": False,
            "expired_reason": "",
        })
    return jobs


def update_runtime(config: dict, added: int, successful: int, total: int, errors: list[str]) -> None:
    now = datetime.now(timezone.utc).astimezone()
    runtime = config.setdefault("runtime", {})
    runtime["last_run"] = now.replace(microsecond=0).isoformat()
    runtime["collection_note"] = (
        f"{now:%Y-%m-%d} 云端采集完成：{successful}/{total} 个公开官方来源成功，新增 {added} 条。"
        + (" 部分来源暂时不可用，已保留原数据。" if errors else "")
    )
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    jobs = []
    errors = []
    successful = 0
    sources = [("search", s) for s in config.get("official_sources", [])]
    sources += [("workday", s) for s in config.get("workday_sources", [])]
    def run_source(entry):
        kind, source = entry
        result = collect_search_source(source) if kind == "search" else collect_workday(source)
        return source, result

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(run_source, entry): entry for entry in sources}
        for future in as_completed(futures):
            kind, source = futures[future]
            try:
                _, result = future.result()
                jobs.extend(result)
                successful += 1
            except Exception as exc:  # one unavailable public source must not stop publication
                errors.append(f"{source.get('company', kind)}: {type(exc).__name__}")
    added = manage_jobs.add(jobs) if jobs else 0
    update_runtime(config, added, successful, len(sources), errors)
    manage_jobs.render()
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "dashboard" / "index.html", PUBLIC_DIR / "index.html")
    print(json.dumps({"collected": len(jobs), "added": added, "successful_sources": successful, "errors": errors}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

