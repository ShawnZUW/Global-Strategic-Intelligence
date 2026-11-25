#!/usr/bin/env python3
"""Collect public RSS/Atom and fixed newsroom headlines with source provenance.

This writes a separate candidate-feed dataset; it never edits curated intelligence.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
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
MAX_ITEMS = 1500
MAX_PER_SOURCE = 40
HTML_PARSER_VERSION = 2
USER_AGENT = "GlobalStrategicIntelligence/1.2 (public source headlines; daily refresh)"
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
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
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
    if not isinstance(value, str) or not value.strip():
        return None
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
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", html.unescape(value or ""))).strip()[:500]


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


class NewsroomLinks(HTMLParser):
    """Read visible headline anchors only; never infer dates from URL paths."""
    def __init__(self, headline_classes=()):
        super().__init__(convert_charrefs=True)
        self.anchor = None
        self.links = []
        self.ignore_depth = 0
        self.stack = []
        self.headline_classes = set(headline_classes)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "template", "noscript"}:
            self.ignore_depth += 1
        if self.ignore_depth:
            return
        if tag == "a":
            self.anchor = {"href": attrs.get("href", ""), "title": attrs.get("title", ""), "text": [], "headlines": [], "published_at": None, "has_body": False}
            self.stack = []
        elif tag == "time" and self.anchor is not None:
            self.anchor["published_at"] = parse_date(attrs.get("datetime"))
        if self.anchor is not None and tag != "a" and tag not in {"img", "br", "hr", "input", "meta", "link", "source", "wbr"}:
            marker = " ".join(str(attrs.get(k) or "") for k in ("class", "id", "itemprop"))
            explicit = (tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
                        or bool(self.headline_classes.intersection((attrs.get("class") or "").split()))
                        or bool(re.search(r"(?:headline|(?:^|[\s_-])(?:title|tit\d*|ttl|heading|subject)(?:$|[\s_-]))", marker, re.I)))
            self.stack.append({"tag": tag, "headline": explicit, "text": []})
            if (tag == "p" and not explicit and not any(x["headline"] for x in self.stack)) or re.search(r"(?:description|excerpt|body|teaser|std_word|nclt_word)", marker, re.I):
                self.anchor["has_body"] = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"} and self.ignore_depth:
            self.ignore_depth -= 1
        if tag == "a" and self.anchor is not None:
            for entry in self.stack:
                if entry["headline"]:
                    self.anchor["headlines"].append(" ".join(entry["text"]))
            self.links.append(self.anchor)
            self.anchor = None
            self.stack = []
        elif self.anchor is not None:
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index]["tag"] == tag:
                    for entry in self.stack[index:]:
                        if entry["headline"]:
                            self.anchor["headlines"].append(" ".join(entry["text"]))
                    self.stack = self.stack[:index]
                    break

    def handle_data(self, data):
        if self.anchor is not None and not self.ignore_depth:
            self.anchor["text"].append(data)
            for entry in self.stack:
                if entry["headline"]:
                    entry["text"].append(data)


def headline_text(value: str, explicit: bool = False) -> str | None:
    """Reject prose instead of truncating it and calling it a headline."""
    value = re.sub(r"\s+", " ", html.unescape(value or "")).strip()
    value = re.sub(r"\s*(?:(?:Read more|Learn more|Find out more|Continue reading|了解更多|阅读更多|View)\s*[→›»]*)+$", "", value, flags=re.I).strip()
    limit = 320 if explicit else 180
    if not 8 <= len(value) <= limit or re.fullmatch(r"[\d\W_]+", value):
        return None
    if value.casefold() in {"press briefings", "news releases", "press releases", "latest news", "company news", "corporate news", "newsroom", "news", "read more", "learn more"}:
        return None
    if not explicit and (len(value.split()) > 28 or re.search(r"[.!?]\s+[A-Z]", value)):
        return None
    return value


def parse_html_listing(payload: bytes, base_url: str, source: dict, encoding="utf-8") -> list[dict]:
    pattern = source.get("link_pattern")
    if not pattern:
        raise ValueError("HTML source requires a verified article-link pattern")
    # CATL's official list was inspected: p.mc_e1_txt is the headline,
    # while sibling div.mc_e1_date is metadata. Do not generalize '*txt'.
    verified_classes = {"www.catl.com": {"mc_e1_txt"}}
    parser = NewsroomLinks(set(source.get("headline_classes", [])) | verified_classes.get(urlsplit(base_url).hostname, set()))
    parser.feed(payload.decode(encoding, errors="replace"))
    hosts = set(source.get("article_allowed_hosts", source["allowed_hosts"]))
    items = {}
    for anchor in parser.links:
        url = normalize_url(anchor["href"], base_url)
        if not url or urlsplit(url).hostname not in hosts or not re.search(pattern, url):
            continue
        candidates = [headline_text(value, explicit=True) for value in anchor["headlines"]]
        title = next((value for value in candidates if value), None) or headline_text(anchor["title"], explicit=True)
        if not title and not anchor["has_body"]:
            title = headline_text(" ".join(anchor["text"]))
        if not title:
            continue
        row = {"title": title, "url": url, "published_at": anchor["published_at"],
               "parser_version": HTML_PARSER_VERSION,
               "source_updated_at": None, "date_note": None if anchor["published_at"] else "列表未提供可核验发布日期；不以发现时间代替"}
        if url not in items or len(title) < len(items[url]["title"]):
            items[url] = row
    if not items:
        raise ValueError("no article headlines matched; page may be dynamic or its layout changed")
    return list(items.values())


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
    method = source.get("method", "rss")
    accept = "text/html,application/xhtml+xml" if method == "html" else "application/rss+xml, application/atom+xml, application/xml, text/xml"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    opener = build_opener(OfficialRedirects(allowed))
    with opener.open(request, timeout=20) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("response exceeds 2 MB limit")
        if response.status != 200:
            raise ValueError(f"unexpected HTTP {response.status}")
        if method == "html":
            encoding = response.headers.get_content_charset() or source.get("encoding", "utf-8")
            result = parse_html_listing(body, response.url, source, encoding)
        else:
            result = parse_feed(body, response.url)
        return result, {"http_status": response.status, "bytes": len(body), "method": method}


def is_relevant(title: str, source: dict) -> bool:
    words = source.get("match_keywords", [])
    if not words:
        return True
    return any((word.casefold() in title.casefold()) if re.search(r"[\u3400-\u9fff]", word)
               else re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", title, re.I) for word in words)


def classify(title: str, source: dict) -> list[str]:
    result = list(source.get("categories", []))
    for category, pattern in CLASSIFIERS.items():
        if re.search(pattern, title, re.I) and category not in result:
            result.append(category)
    return result


def source_metadata(source: dict) -> dict:
    """Source identity is not evidence that a particular headline has been verified."""
    tier = source.get("source_tier", "primary")
    labels = {
        "primary": "原始披露线索",
        "research": "专业研究线索",
        "media": "专业媒体线索",
        "community": "社区讨论线索",
    }
    if tier not in labels:
        raise ValueError("source_tier must be primary, research, media or community")
    return {"publisher_id": source.get("publisher_id", source["id"]),
            "publisher_type": source.get("publisher_type"),
            "source_tier": tier, "evidence_level": labels[tier]}


def source_limit(source: dict) -> int:
    value = source.get("max_items", MAX_PER_SOURCE)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_items must be a positive integer")
    return min(value, MAX_PER_SOURCE)


def collect(config: dict, previous: dict, state: dict, now: datetime, fetcher=fetch_source) -> tuple[dict, dict]:
    stamp = iso(now)
    old_sources = {x["id"]: x for x in previous.get("sources", [])}
    current_sources = {x["id"]: x for x in config["sources"]}
    metadata = {key: source_metadata(source) for key, source in current_sources.items()}
    limits = {key: source_limit(source) for key, source in current_sources.items()}
    seen = dict(state.get("seen", {}))
    items = {}
    # Retain previously displayed signals on transient source failure or feed rollover.
    for old in previous.get("items", []):
        if old.get("source_id") not in current_sources:
            continue
        # Retain fingerprints, but never republish an old untrusted HTML title.
        seen.setdefault(old["id"], {"first_seen_at": old["first_seen_at"]})
        if current_sources[old["source_id"]].get("method") == "html" and old.get("parser_version") != HTML_PARSER_VERSION:
            continue
        key = normalize_url(old.get("url", ""))
        if key:
            # Update source classification, but never the retained observation timestamps.
            old = dict(old, url=key, **metadata[old["source_id"]])
            items[key] = old
            seen.setdefault(old["id"], {"first_seen_at": old["first_seen_at"]})
    audits = []

    def request(source):
        try:
            data, details = fetcher(source)
            return source, data, details, None
        except (HTTPError, URLError, TimeoutError, OSError, ET.ParseError, ValueError, LookupError) as exc:
            # No response bodies, credentials, or full article text in logs/audits.
            return source, [], {}, (f"{type(exc).__name__}: {exc}")[:240]

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(config["sources"])))) as pool:
        for source, raw_items, details, error in pool.map(request, config["sources"]):
            matching = [row for row in raw_items if is_relevant(row["title"], source)]
            audit = {"id": source["id"], "name": source["name"], "url": source["url"],
                     "homepage": source.get("homepage"), **metadata[source["id"]],
                     "method": source.get("method", "rss"), "max_items": limits[source["id"]],
                     "initial_baseline": not old_sources.get(source["id"], {}).get("last_success_at"),
                     "coverage_note": source.get("coverage_note"),
                     "status": "failed" if error else "success", "checked_at": stamp,
                     "last_success_at": old_sources.get(source["id"], {}).get("last_success_at") if error else stamp,
                     "item_count": len(raw_items), "relevant_count": len(matching),
                     "latest_publication_at": max((x["published_at"] for x in raw_items if x["published_at"]), default=None),
                     "error": error, **details}
            audits.append(audit)
            for row in matching[:limits[source["id"]]]:
                key = row["url"]
                identity = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                record = seen.setdefault(identity, {"first_seen_at": stamp})
                row = {**row, "id": identity, "source_id": source["id"], "source_name": source["name"],
                       "source_url": source["url"], **metadata[source["id"]],
                       "first_seen_at": record["first_seen_at"], "last_seen_at": stamp,
                       "categories": classify(row["title"], source),
                       "collection_method": source.get("method", "rss"),
                       "status": "待核验"}
                # If two feeds point to the same canonical page, keep one signal.
                if key in items:
                    row["first_seen_at"] = min(items[key]["first_seen_at"], row["first_seen_at"])
                    record["first_seen_at"] = row["first_seen_at"]
                items[key] = row
    # Per-source budgets prevent a high-volume feed from hiding smaller specialist publishers.
    budget = min(MAX_PER_SOURCE, max(1, MAX_ITEMS // max(1, len(current_sources))))
    ranked = sorted(items.values(), key=lambda x: (x.get("published_at") or "", x["first_seen_at"], x["id"]), reverse=True)
    kept_per_source = {}
    ordered = []
    for row in ranked:
        source_id = row["source_id"]
        if kept_per_source.get(source_id, 0) < min(budget, limits[source_id]):
            ordered.append(row)
            kept_per_source[source_id] = kept_per_source.get(source_id, 0) + 1
    success_count = sum(x["status"] == "success" for x in audits)
    baseline = not state.get("seen") and not previous.get("items")
    new_count = sum(x["first_seen_at"] == stamp for x in ordered)
    data = {"meta": {"schema_version": 1, "generated_at": stamp,
                     "as_of": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                     "mode": "tiered-public-source-leads", "collection_status": "success" if success_count == len(audits) else ("partial" if success_count else "failed"),
                     "note": "标题来自原始披露、专业研究、媒体或社区RSS及固定新闻列表，逐条保留来源层级；关键词分类不构成事实核验。未提供发布日期的条目保留空值，首次发现时间不是事件发生时间。社区与媒体线索须回原始资料核验后才进入主面板结论。",
                     "source_count": len(audits), "successful_sources": success_count,
                     "item_count": len(ordered), "newly_discovered_count": new_count,
                     "discovery_count_label": "本次首次发现（含新源历史建库，非今日发生事件）",
                     "baseline_source_count": sum(x["initial_baseline"] for x in audits),
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
