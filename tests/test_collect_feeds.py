"""Behavioral tests for provenance, deduplication and failure preservation."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("collect_feeds", Path(__file__).resolve().parents[1] / "scripts" / "collect_feeds.py")
feeds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(feeds)

SOURCE = {"id": "official", "name": "Official Test Publisher", "url": "https://official.example/feed",
          "allowed_hosts": ["official.example"], "categories": ["技术与竞对"], "match_keywords": []}
NOW = datetime(2026, 11, 25, 13, 0, tzinfo=timezone.utc)
RSS = b'''<rss version="2.0"><channel>
<item><title>Battery partnership</title><link>https://official.example/article?a=1&amp;utm_source=rss#top</link><pubDate>Tue, 24 Nov 2026 09:00:00 EST</pubDate><description>Do not copy this article.</description></item>
<item><title>Undated update</title><link>https://official.example/undated</link></item>
<item><title>Unsafe link</title><link>javascript:alert(1)</link></item>
</channel></rss>'''


class FeedTests(unittest.TestCase):
    def fetch(self, source):
        return feeds.parse_feed(RSS, source["url"]), {"http_status": 200, "bytes": len(RSS)}

    def test_publication_time_is_not_collection_time_and_no_fulltext(self):
        data, _ = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, self.fetch)
        indexed = {x["url"]: x for x in data["items"]}
        self.assertEqual(len(indexed), 2)
        self.assertEqual(indexed["https://official.example/article?a=1"]["published_at"], "2026-11-24T14:00:00Z")
        self.assertIsNone(indexed["https://official.example/undated"]["published_at"])
        self.assertNotIn("description", json.dumps(data))
        self.assertTrue(data["meta"]["initial_baseline"])
        self.assertEqual(data["items"][0]["status"], "待核验")

    def test_duplicate_tracking_urls_and_first_seen_survive_second_run(self):
        initial, state = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, self.fetch)

        def duplicates(source):
            rows, details = self.fetch(source)
            rows.append(dict(rows[0]))
            return rows, details

        updated, state2 = feeds.collect({"sources": [SOURCE]}, initial, state, NOW + timedelta(days=1), duplicates)
        self.assertEqual(len(updated["items"]), 2)
        self.assertEqual(updated["meta"]["newly_discovered_count"], 0)
        self.assertFalse(updated["meta"]["initial_baseline"])
        for row in updated["items"]:
            self.assertEqual(row["first_seen_at"], feeds.iso(NOW))
            self.assertEqual(row["last_seen_at"], feeds.iso(NOW + timedelta(days=1)))
        self.assertEqual(state["seen"], state2["seen"])

    def test_failed_source_retains_old_items_without_fresh_last_seen(self):
        initial, state = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, self.fetch)

        def unavailable(source):
            raise TimeoutError("source timeout")

        failed, _ = feeds.collect({"sources": [SOURCE]}, initial, state, NOW + timedelta(days=1), unavailable)
        self.assertEqual(failed["meta"]["collection_status"], "failed")
        self.assertEqual(failed["meta"]["newly_discovered_count"], 0)
        self.assertEqual(failed["items"], initial["items"])
        self.assertEqual(failed["sources"][0]["last_success_at"], feeds.iso(NOW))
        self.assertIn("TimeoutError", failed["sources"][0]["error"])

    def test_seen_state_survives_item_not_in_latest_snapshot(self):
        initial, state = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, self.fetch)
        restored, _ = feeds.collect({"sources": [SOURCE]}, {"items": []}, state, NOW + timedelta(days=40), self.fetch)
        self.assertEqual(restored["meta"]["newly_discovered_count"], 0)
        self.assertEqual({r["first_seen_at"] for r in restored["items"]}, {feeds.iso(NOW)})

    def test_atom_updated_is_not_mislabeled_as_publication(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Solid-state cell</title><link rel="alternate" href="/post"/><updated>2026-11-25T12:00:00Z</updated></entry></feed>'''
        row = feeds.parse_feed(atom, SOURCE["url"])[0]
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["source_updated_at"], "2026-11-25T12:00:00Z")
        self.assertEqual(row["url"], "https://official.example/post")
        self.assertIsNone(feeds.parse_date("2026-11-25 12:00:00"))

    def test_invalid_or_entity_xml_and_nonofficial_redirect_rejected(self):
        for data in [b"", b"<html><body>Access denied</body></html>", b'<!DOCTYPE rss [<!ENTITY x "expanded">]><rss>&x;</rss>']:
            with self.assertRaises(ValueError):
                feeds.parse_feed(data, SOURCE["url"])
        handler = feeds.OfficialRedirects({"official.example"})
        with self.assertRaises(ValueError):
            handler.redirect_request(None, None, 302, "Moved", {}, "http://127.0.0.1/private")
        self.assertIsNone(feeds.normalize_url("https://user:secret@official.example/private"))

    def test_history_is_last_thirty_calendar_days_and_newest_first(self):
        data, state = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, self.fetch)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = json.loads(json.dumps(data))
            old["meta"]["as_of"] = "2026-10-26"
            feeds.save_outputs(root, old, state)
            yesterday = json.loads(json.dumps(data))
            yesterday["meta"]["as_of"] = "2026-11-24"
            feeds.save_outputs(root, yesterday, state)
            feeds.save_outputs(root, data, state)
            manifest = feeds.read_json(root / "feed-history" / "manifest.json", {})
            self.assertEqual([x["date"] for x in manifest["days"]], ["2026-11-25", "2026-11-24"])
            self.assertFalse((root / "feed-history" / "2026-10-26.json").exists())
            self.assertFalse((root / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
