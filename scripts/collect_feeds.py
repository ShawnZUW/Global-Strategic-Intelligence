#!/usr/bin/env python3
"""Collect public official RSS/Atom headlines. Python 3.11+, standard library only.

This writes a separate candidate-feed dataset; it never edits curated intelligence.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

UTC = timezone.utc
MAX_BYTES = 2_000_000
MAX_ITEMS = 200
MAX_PER_SOURCE = 60
USER_AGENT = "GlobalStrategicIntelligence/1.0 (public RSS headlines; daily refresh)"
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
CLASSIFIERS = {
    "航道与物流": r"\b(shipping|maritime|chokepoint|strait|canal|red sea|port|logistics)\b",
    "矿产与原材料": r"\b(lithium|nickel|cobalt|graphite|copper|mineral|mining|mine|raw material)\b",
    "能源与供需": r"\b(energy|oil|gas|electricity|power|supply|demand|storage|renewable)\b",
    "技术与竞对": r"\b(battery|batteries|solid.state|cell|cathode|anode|technology|production line)\b",
    "合作与投资": r"\b(partner|partnership|agreement|joint|invest|investment|acquisition)\b",
    "地缘与贸易": r"\b(conflict|war|ceasefire|sanction|tariff|trade|ukraine|sudan|yemen|gaza|iran)\b",
}


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(value: str | None) -> str | None:
    """Do not use collection time as an unknown publication time."""
    if not value or not value.strip():
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        return None
    return iso(parsed)


def normalize_url(value: str, base: str = "") -> str | None:
    try:
        parts = urlsplit(urljoin(base, value.strip()))
        if parts.scheme.lower() not in {"https", "http"} or not parts.hostname:
            return None
        if parts.username or parts.password:
            return None
        host = parts.hostname.lower()
        port = parts.port
        if port and not (parts.scheme == "https" and port == 443) and not (parts.scheme == "http" and port == 80):
            host += ":" + str(port)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", urlencode(query), ""))
    except (ValueError, TypeError):
        return None


def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", html.unescape(value))).strip()[:500]


def child_text(node: ET.Element, names: tuple[str, ...]) -> str | None:
    for child in node:
        if child.tag.rsplit("}", 1)[-1] in names and child.text:
            return "".join(child.itertext()).strip()
    return None


def parse_feed(payload: bytes, base_url: str) -> list[dict]:
    if not payload.strip():
        raise ValueError("empty response body")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD/entity declarations are not accepted")
    root = ET.fromstring(payload)
    if root.tag.rsplit("}", 1)[-1] not in {"rss", "feed", "RDF"}:
        raise ValueError("response is not an RSS/Atom feed")
    items = []
    for node in root.iter():
        kind = node.tag.rsplit("}", 1)[-1]
        if kind not in {"item", "entry"}:
            continue
        title = clean_title(child_text(node, ("title",)) or "")
        raw_link = child_text(node, ("link",))
        if kind == "entry":
            for child in node:
                if child.tag.rsplit("}", 1)[-1] == "link" and child.get("rel", "alternate") == "alternate":
                    raw_link = child.get("href") or raw_link
                    break
        link = normalize_url(raw_link or "", base_url) if raw_link else None
        if not title or not link:
            continue
        # Atom 'updated' is not necessarily the original publication time.
        raw_date = child_text(node, ("pubDate", "published", "date"))
        items.append({"title": title, "url": link, "published_at": parse_date(raw_date),
                      "source_updated_at": parse_date(child_text(node, ("updated",)))})
    return items


class OfficialRedirects(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts or parsed.username or parsed.password:
            raise ValueError("redirect outside configured official HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_source(source: dict) -> tuple[list[dict], dict]:
    url = source["url"]
    parsed = urlsplit(url)
    allowed = set(source["allowed_hosts"])
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise ValueError("source must use its configured official HTTPS host")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    opener = build_opener(OfficialRedirects(allowed))
    with opener.open(request, timeout=20) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("response exceeds 2 MB limit")
        if response.status != 200:
            raise ValueError(f"unexpected HTTP {response.status}")
        result = parse_feed(body, response.url)
        return result, {"http_status": response.status, "bytes": len(body)}


def is_relevant(title: str, source: dict) -> bool:
    words = source.get("match_keywords", [])
    if not words:
        return True
    return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", title, re.I) for word in words)


def classify(title: str, source: dict) -> list[str]:
    result = list(source.get("categories", []))
    for category, pattern in CLASSIFIERS.items():
        if re.search(pattern, title, re.I) and category not in result:
            result.append(category)
    return result


def collect(config: dict, previous: dict, state: dict, now: datetime, fetcher=fetch_source) -> tuple[dict, dict]:
    stamp = iso(now)
    old_sources = {x["id"]: x for x in previous.get("sources", [])}
    current_sources = {x["id"]: x for x in config["sources"]}
    seen = dict(state.get("seen", {}))
    items = {}
    # Retain previously displayed signals on transient source failure or feed rollover.
    for old in previous.get("items", []):
        if old.get("source_id") not in current_sources:
            continue
        key = normalize_url(old.get("url", ""))
        if key:
            old = dict(old, url=key)
            items[key] = old
            seen.setdefault(old["id"], {"first_seen_at": old["first_seen_at"]})
    audits = []

    def request(source):
        try:
            data, details = fetcher(source)
            return source, data, details, None
        except (HTTPError, URLError, TimeoutError, OSError, ET.ParseError, ValueError) as exc:
            # No response bodies, credentials, or full article text in logs/audits.
            return source, [], {}, (f"{type(exc).__name__}: {exc}")[:240]

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(config["sources"])))) as pool:
        for source, raw_items, details, error in pool.map(request, config["sources"]):
            matching = [row for row in raw_items if is_relevant(row["title"], source)]
            audit = {"id": source["id"], "name": source["name"], "url": source["url"],
                     "homepage": source.get("homepage"), "publisher_type": source.get("publisher_type"),
                     "coverage_note": source.get("coverage_note"),
                     "status": "failed" if error else "success", "checked_at": stamp,
                     "last_success_at": old_sources.get(source["id"], {}).get("last_success_at") if error else stamp,
                     "item_count": len(raw_items), "relevant_count": len(matching),
                     "latest_publication_at": max((x["published_at"] for x in raw_items if x["published_at"]), default=None),
                     "error": error, **details}
            audits.append(audit)
            for row in matching[:MAX_PER_SOURCE]:
                key = row["url"]
                identity = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                record = seen.setdefault(identity, {"first_seen_at": stamp})
                row = {**row, "id": identity, "source_id": source["id"], "source_name": source["name"],
                       "source_url": source["url"], "publisher_type": source.get("publisher_type"),
                       "first_seen_at": record["first_seen_at"], "last_seen_at": stamp,
                       "categories": classify(row["title"], source),
                       "evidence_level": "官方订阅线索", "status": "待核验"}
                # If two feeds point to the same canonical page, keep one signal.
                if key in items:
                    row["first_seen_at"] = min(items[key]["first_seen_at"], row["first_seen_at"])
                    record["first_seen_at"] = row["first_seen_at"]
                items[key] = row
    ordered = sorted(items.values(), key=lambda x: (x.get("published_at") or "", x["first_seen_at"], x["id"]), reverse=True)[:MAX_ITEMS]
    success_count = sum(x["status"] == "success" for x in audits)
    baseline = not state.get("seen") and not previous.get("items")
    new_count = sum(x["first_seen_at"] == stamp for x in ordered)
    data = {"meta": {"schema_version": 1, "generated_at": stamp,
                     "as_of": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                     "mode": "official-feed-leads", "collection_status": "success" if success_count == len(audits) else ("partial" if success_count else "failed"),
                     "note": "标题来自官方订阅，关键词分类仅供筛选，未经逐条核验。首次发现时间不是事件发生时间，企业表述不代表独立验证。",
                     "source_count": len(audits), "successful_sources": success_count,
                     "item_count": len(ordered), "newly_discovered_count": new_count,
                     "initial_baseline": baseline, "baseline_note": "首次建库，所见旧公告不视为今日新增事件。" if baseline else None,
                     "schedule": "每日北京时间约07:40；GitHub调度可能延迟。"},
            "items": ordered, "sources": audits}
    return data, {"schema_version": 1, "updated_at": stamp, "seen": seen}


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    # Corrupt state is an error: silently resetting it would falsify first-seen dates.
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_outputs(data_dir: Path, data: dict, state: dict) -> None:
    write_json(data_dir / "feed-latest.json", data)
    write_json(data_dir / "feed-state.json", state)
    history_dir = data_dir / "feed-history"
    date = data["meta"]["as_of"]
    write_json(history_dir / (date + ".json"), data)
    cutoff = datetime.fromisoformat(date).date() - timedelta(days=29)
    records = []
    for file in sorted(history_dir.glob("????-??-??.json"), reverse=True):
        if file.stem < cutoff.isoformat():
            file.unlink()
            continue
        snapshot = read_json(file, {})
        meta = snapshot.get("meta", {})
        records.append({"date": file.stem, "path": "data/feed-history/" + file.name,
                        "generated_at": meta.get("generated_at"), "item_count": meta.get("item_count", 0),
                        "collection_status": meta.get("collection_status")})
    write_json(history_dir / "manifest.json", {"updated_at": data["meta"]["generated_at"], "retention_days": 30, "days": records})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    args = parser.parse_args()
    config = read_json(args.data_dir / "feed_sources.json", {})
    if not config.get("sources"):
        parser.error("feed_sources.json requires at least one source")
    previous = read_json(args.data_dir / "feed-latest.json", {})
    state = read_json(args.data_dir / "feed-state.json", {})
    data, state = collect(config, previous, state, datetime.now(UTC))
    save_outputs(args.data_dir, data, state)
    print(json.dumps({"generated_at": data["meta"]["generated_at"], "status": data["meta"]["collection_status"],
                      "items": data["meta"]["item_count"], "newly_discovered": data["meta"]["newly_discovered_count"],
                      "sources": [{"name": x["name"], "status": x["status"], "items": x["relevant_count"], "error": x["error"]} for x in data["sources"]]}, ensure_ascii=False))
    return 0 if data["meta"]["successful_sources"] else 1


if __name__ == "__main__":
    sys.exit(main())
