#!/usr/bin/env python3
"""Check evidence links and semantic boundaries before publishing curated content."""
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

def read(name):
    return json.loads((ROOT / "data" / name).read_text())

def check_sources(bundle):
    refs = bundle["sources"]
    ids = {x["id"] for x in refs}
    assert len(ids) == len(refs), "duplicate evidence source id"
    for source in refs:
        url = urlsplit(source["url"])
        assert url.scheme in ("https", "http") and url.hostname, "invalid evidence URL"
    return ids

def citations(item, ids, required=True):
    refs = item.get("source_ids", [])
    assert (bool(refs) or not required) and set(refs) <= ids, "missing or unresolved citation: " + str(item.get("id", item.get("text", "")))[:120]

chain, insights, facts = read("chain.json"), read("insights.json"), read("latest.json")
chain_refs, insight_refs = check_sources(chain), check_sources(insights)
fact_refs = {x['id'] for x in facts['sources'] if x.get('id')}
nodes = {n["id"]: n for n in chain["nodes"]}
assert len(nodes) == len(chain["nodes"]), "duplicate chain node"
routes = {r["id"] for r in chain["routes"]}
for node in nodes.values():
    assert node["stage"] in range(7)
    assert set(node["routes"]) <= routes
    assert node["title"] and node["process"] and node["outputs"]
    citations(node, chain_refs)
edges = chain["edges"]
assert len({(e["from"], e["to"]) for e in edges}) == len(edges), "duplicate chain relation"
for edge in edges:
    assert edge["from"] in nodes and edge["to"] in nodes
    assert set(edge["routes"]) <= routes
for section in ["partners", "glossary", "pack_comparison", "insights"]:
    for item in chain[section]:
        citations(item, chain_refs)
for partner in chain["partners"]:
    assert partner["material_label"] and partner["fact"] and partner["status"]
assert not any(e["from"] in {"hpal", "rkef", "ncm_salts", "pcam"} and e["to"] in {"lfp", "lmfp"} for e in edges)
assert any(e["from"] == "mn_salt" and e["to"] == "lmfp" for e in edges)
assert not any(e["to"] in {"na_cathode", "na_cell"} and e["from"] in {"li_carbonate", "li_hydroxide", "electrolyte", "collectors", "natural_anode", "synthetic_anode"} for e in edges)
event_ids = {e["id"] for e in facts["events"]}
assert len(event_ids) == len(facts["events"]), "duplicate fact id"
story_ids = {s['id'] for s in insights['insights']}
assert len(story_ids) == len(insights['insights']), 'duplicate insight id'
for story in insights["insights"]:
    assert all(story.get(k) for k in ["id", "title", "thesis", "why_now", "timeline", "facts", "effect_chain", "catl_relevance", "watch_signals", "management_question"])
    citations(story, insight_refs)
    assert len(set(story["source_ids"])) >= 2, "deep analysis requires multiple sources"
    assert set(story.get("related_event_ids", [])) <= event_ids
    assert set(story.get('chain_node_ids', [])) <= nodes.keys(), 'unknown chemistry node in insight'
    assert set(story.get('chain_routes', [])) <= routes, 'unknown chemistry route in insight'
    for section in ["facts", "timeline", "effect_chain", "watch_signals", "material_exposure", "decision_checkpoints"]:
        for item in story.get(section, []):
            citations(item, insight_refs)
    for signal in story['watch_signals']:
        assert all(signal.get(k) for k in ['indicator', 'interpretation', 'observation_source', 'frequency', 'decision_use']), 'incomplete decision observation'
    for checkpoint in story.get('decision_checkpoints', []):
        assert all(isinstance(checkpoint.get(k), str) and checkpoint[k].strip() for k in ['signal', 'current_reading', 'upgrade_when', 'downgrade_when', 'decision_use']), 'incomplete judgment update condition'
    assert "待补充" not in json.dumps(story, ensure_ascii=False)

transmission = chain.get('risk_transmission', [])
assert len({r['id'] for r in transmission}) == len(transmission), 'duplicate material transmission id'
for row in transmission:
    assert all(isinstance(row.get(k), str) and row[k].strip() for k in ['id', 'material', 'forms', 'direct_effect', 'indirect_effect', 'boundary', 'decision_use']), 'incomplete material transmission'
    assert row.get('public_signals') and all(isinstance(s, str) and s.strip() for s in row['public_signals']), 'missing material signals'
    assert row.get('chain_routes') and set(row['chain_routes']) <= routes, 'unknown material route'
    assert row.get('chain_node_ids') and set(row['chain_node_ids']) <= nodes.keys(), 'unknown material node'
    assert set(row.get('related_insight_ids', [])) <= story_ids, 'unknown material analysis link'
    citations(row, chain_refs)
if 'risk_transmission_count' in chain['meta']:
    assert chain['meta']['risk_transmission_count'] == len(transmission), 'material transmission count drift'
if 'decision_checkpoint_count' in insights['meta']:
    assert insights['meta']['decision_checkpoint_count'] == sum(len(s.get('decision_checkpoints', [])) for s in insights['insights']), 'judgment condition count drift'

history = facts.get('price_history', [])
price_keys = [(p['series_id'], p['date'], p['unit']) for p in history]
assert len(set(price_keys)) == len(price_keys), 'duplicate historical price observation'
history_map = dict(zip(price_keys, history))
for point in facts.get('prices', []) + history:
    assert isinstance(point.get('value'), (int, float)) and math.isfinite(point['value']) and point['value'] > 0, 'invalid price'
    assert point.get('series_id') and point.get('material') and point.get('unit'), 'price missing specification'
    observed = date.fromisoformat(point['date'])
    assert observed <= date.fromisoformat(facts['meta']['as_of']), 'future observed price'
    if point.get('source_doc_date'):
        assert observed <= date.fromisoformat(point['source_doc_date']), 'price observation after source report'
    url = urlsplit(point['source_url'])
    assert url.scheme in ('http', 'https') and url.hostname, 'price source URL missing'
    if point.get('source_id'):
        assert point['source_id'] in insight_refs | fact_refs, 'price evidence source unresolved'
    if point.get('related_insight_id'):
        assert point['related_insight_id'] in story_ids, 'price analysis unresolved'
    assert set(point.get('chain_node_ids', [])) <= nodes.keys(), 'price chemistry node unresolved'
    if point.get('chain_route'):
        assert point['chain_route'] in routes | {'all'}, 'price chemistry route unresolved'
    if point.get('comparison_date'):
        assert date.fromisoformat(point['comparison_date']) < observed, 'invalid price comparison date'
        prior = history_map.get((point['series_id'], point['comparison_date'], point['unit']))
        if prior and point.get('change_pct') is not None:
            computed = (point['value'] / prior['value'] - 1) * 100
            assert abs(computed - point['change_pct']) < .02, 'price change disagrees with comparable observations'

catalog = read('source-catalog.json')
publishers = catalog['sources']
assert catalog['meta']['source_count'] == len(publishers), 'publisher count drift'
assert catalog['meta']['research_publisher_count'] == sum(not p.get('automation_enabled') and p.get('method') != 'registry' for p in publishers), 'research publisher count drift'
assert insights['meta']['insight_count'] == len(story_ids)
assert insights['meta']['source_count'] == len(insight_refs)
print('Validated:', len(nodes), 'chain nodes,', len(edges), 'relations,', len(transmission), 'material groups,', len(story_ids), 'evidence-linked analyses,', len(event_ids), 'facts,', len(facts.get('prices', [])), 'current prices and', len(history), 'historical observations.')
