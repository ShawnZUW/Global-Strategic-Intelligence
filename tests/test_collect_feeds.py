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

    def test_html_listing_excludes_navigation_and_does_not_invent_dates(self):
        source = dict(SOURCE, method="html", link_pattern=r"/news/[^/]+$")
        payload = '''<!doctype html><html><nav><a href="/about">About this publisher</a><a href title>Empty attributes</a></nav>
        <a href="/news/battery-project">Battery project begins <time datetime="2026-11-24">24 November</time></a>
        <a href="/news/2026-11-25-plan">A development plan with no stated date</a>
        <a href="https://unrelated.example/news/spam">A different publisher headline</a>
        <script>var bait = '<a href="/news/bait">Injected navigation text</a>';</script></html>'''.encode()
        rows = feeds.parse_html_listing(payload, SOURCE["url"], source)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["published_at"], "2026-11-24")
        self.assertIsNone(rows[1]["published_at"])
        with self.assertRaises(ValueError):
            feeds.parse_html_listing(b"<html><p>Loading news...</p></html>", SOURCE["url"], source)

    def test_specialist_source_is_retained_beside_high_volume_publisher(self):
        specialist = dict(SOURCE, id="specialist")
        def news(source):
            count = 80 if source["id"] == "official" else 1
            return [{"title": "Verified listing headline " + str(i),
                     "url": "https://official.example/" + source["id"] + "/" + str(i),
                     "published_at": "2026-11-24T00:00:00Z" if count > 1 else None,
                     "source_updated_at": None} for i in range(count)], {"http_status": 200}
        data, _ = feeds.collect({"sources": [SOURCE, specialist]}, {}, {}, NOW, news)
        self.assertEqual(sum(x["source_id"] == "specialist" for x in data["items"]), 1)
        self.assertLessEqual(sum(x["source_id"] == "official" for x in data["items"]), feeds.MAX_PER_SOURCE)

    def test_media_and_community_provenance_never_becomes_official_evidence(self):
        media = dict(SOURCE, id="media", publisher_type="专业媒体", source_tier="media")
        community = dict(SOURCE, id="community", publisher_type="论坛社区", source_tier="community")

        def news(source):
            return [{"title": "LFP cell testing discussion", "url": source["url"] + "/" + source["id"],
                     "published_at": None, "source_updated_at": None}], {"http_status": 200}

        initial, state = feeds.collect({"sources": [media, community]}, {}, {}, NOW, news)
        for row in initial["items"] + initial["sources"]:
            self.assertIn(row["source_tier"], {"media", "community"})
            self.assertNotIn("官方", row["evidence_level"])
            self.assertEqual(row["publisher_type"], "专业媒体" if row["source_tier"] == "media" else "论坛社区")
        def unavailable(source):
            raise TimeoutError("source timeout")
        failed, _ = feeds.collect({"sources": [media, community]}, initial, state, NOW + timedelta(days=1), unavailable)
        self.assertEqual(failed["items"], initial["items"])

    def test_source_limit_caps_new_and_retained_items_without_changing_first_seen(self):
        source = dict(SOURCE, source_tier="community", max_items=8)
        def news(s):
            return [{"title": "LFP balancing observation " + str(i),
                     "url": "https://official.example/observation/" + str(i),
                     "published_at": "2026-11-24T00:00:00Z", "source_updated_at": None}
                    for i in range(12)], {"http_status": 200}
        limited, _ = feeds.collect({"sources": [source]}, {}, {}, NOW, news)
        self.assertEqual(len(limited["items"]), 8)
        self.assertEqual(limited["sources"][0]["max_items"], 8)
        self.assertEqual(limited["sources"][0]["relevant_count"], 12)
        initial, state = feeds.collect({"sources": [dict(source, max_items=40)]}, {}, {}, NOW, news)
        def unavailable(s):
            raise TimeoutError("source timeout")
        failed, state2 = feeds.collect({"sources": [source]}, initial, state, NOW + timedelta(days=1), unavailable)
        self.assertEqual(len(failed["items"]), 8)
        self.assertEqual(state2["seen"], state["seen"])
        self.assertTrue(all(r["first_seen_at"] == feeds.iso(NOW) and r["last_seen_at"] == feeds.iso(NOW)
                            for r in failed["items"]))
        self.assertEqual(failed["sources"][0]["last_success_at"], feeds.iso(NOW))

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

    def test_real_sdi_and_huayou_card_structures_keep_only_headlines(self):
        # Structures observed on the official newsroom lists on 2026-11-25.
        source = dict(SOURCE, method="html", link_pattern=r"/(?:global/click\?seq=\d+|en/news/corporate-news/\d+)$")
        markup = '''<a href="/global/click?seq=484" class="swiper-slide"><span class="image"></span><span class="summary"><span class="title">SAMSUNG SDI Ulsan Plant Wins Top Award at 2026 Green Management Awards</span><span class="text">SAMSUNG SDI today announced that its Ulsan plant has received an award. This entire article summary must never be copied as the title.</span></span></a>
        <a href="/en/news/corporate-news/484" title="Huayou Cobalt Adds Two More Provincial-Level Enterprise Technology Centers"><div class="news_cont_list_text"><div class="nclt_tit"><p class="std_tit6">Huayou Cobalt Adds Two More Provincial-Level Enterprise Technology Centers</p></div><div class="nclt_word std_word"><p>Recently, a department released a long list of newly accredited centers. This excerpt is not the title.</p></div><div class="nclt_date">2026-11-04</div></div></a>'''
        rows = feeds.parse_html_listing(markup.encode(), SOURCE["url"], source)
        self.assertEqual([r["title"] for r in rows], ["SAMSUNG SDI Ulsan Plant Wins Top Award at 2026 Green Management Awards", "Huayou Cobalt Adds Two More Provincial-Level Enterprise Technology Centers"])
        self.assertTrue(all(r["parser_version"] == feeds.HTML_PARSER_VERSION for r in rows))
        with self.assertRaises(ValueError):
            feeds.parse_html_listing(b'<a href="/global/click?seq=1"><p>Short article summary. It should never become a title.</p></a>', SOURCE["url"], source)
        self.assertIsNone(feeds.headline_text("Press Briefings"))
        self.assertIsNone(feeds.headline_text("Long prose " * 60))

    def test_legacy_html_removed_but_fingerprint_survives_refresh(self):
        source = dict(SOURCE, method="html", link_pattern=r"/article")
        old, state = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, self.fetch)
        for row in old["items"]:
            row["collection_method"] = "html"
            row["title"] = "Legacy untrusted text " * 20

        def refreshed(s):
            return feeds.parse_html_listing(b'<a href="https://official.example/article?a=1"><h3>Verified headline structure</h3><p>Do not copy this text.</p></a>', SOURCE["url"], source), {"http_status": 200}

        data, state2 = feeds.collect({"sources": [source]}, old, state, NOW + timedelta(days=1), refreshed)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["title"], "Verified headline structure")
        self.assertEqual(data["items"][0]["first_seen_at"], feeds.iso(NOW))
        self.assertEqual(state2["seen"], state["seen"])
        self.assertEqual(data["meta"]["newly_discovered_count"], 0)

    def test_new_source_baseline_persists_after_an_initial_failure(self):
        def unavailable(source):
            raise TimeoutError("unavailable")
        failed, state = feeds.collect({"sources": [SOURCE]}, {}, {}, NOW, unavailable)
        data, _ = feeds.collect({"sources": [SOURCE]}, failed, state, NOW + timedelta(days=1), self.fetch)
        self.assertTrue(data["sources"][0]["initial_baseline"])
        self.assertEqual(data["meta"]["baseline_source_count"], 1)

    def test_catl_verified_headline_class_excludes_sibling_date(self):
        source = dict(SOURCE, id="catl", allowed_hosts=["www.catl.com"], method="html", link_pattern=r"/en/news/\d+\.html$")
        markup = '<a href="/en/news/7084.html" class="mc_e1_lisbox"><div class="mc_e1_imgbox"><img src="image.jpg"></div><div class="mc_e1_txtbox"><p class="mc_e1_txt">CATL Opens Türkiye\'s First NING SERVICE Experience Center in Istanbul</p><div class="mc_e1_date">11/19/2026</div></div></a>'
        row = feeds.parse_html_listing(markup.encode(), "https://www.catl.com/en/news/", source)[0]
        self.assertEqual(row["title"], "CATL Opens Türkiye's First NING SERVICE Experience Center in Istanbul")
        self.assertIsNone(row["published_at"])


if __name__ == "__main__":
    unittest.main()
