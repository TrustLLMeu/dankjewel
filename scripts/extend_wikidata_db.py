#!/usr/bin/env python3
"""Extend an existing Wikidata SQLite DB with entities extracted from claim text.

The oracle DB built by build_fever_wikidata.py only contains entities from
FEVER evidence annotations.  Many claims reference entities (subjects AND
objects) that are NOT in the evidence pages — for example the claim
"Chris Paul is a two-time Olympic gold winner" references Chris Paul, whose
Wikipedia page may not have been annotated as evidence.

This script bridges that gap:

  1. Read a set of FEVER-style claims (JSONL).
  2. Extract named entities from the claim text with spaCy NER.
  3. Also pull subject/object entity names out via ClaimExtractor so that
     structurally important entities get added even without NER tags.
  4. Resolve entity names → Wikipedia → Wikidata QIDs (batched, cached).
  5. Fetch entity data (labels, aliases, claims for a broad property list).
  6. INSERT OR REPLACE into an existing SQLite DB — does NOT rebuild it.

Usage:
    # Extend the oracle DB with entities from oracle claims
    python scripts/extend_wikidata_db.py \\
        --claims  data/fever2_oracle_sample.jsonl \\
        --db-path data/wikidata_fever.db

    # Extend from a different claim file, into a custom DB
    python scripts/extend_wikidata_db.py \\
        --claims  data/fever2_sample.jsonl \\
        --db-path data/wikidata_fever.db \\
        --max-entities 200

    # Dry-run: just show which entities would be fetched
    python scripts/extend_wikidata_db.py \\
        --claims  data/fever2_oracle_sample.jsonl \\
        --db-path data/wikidata_fever.db \\
        --dry-run
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "FEVER-Eval-Research/1.0 (academic; extend_wikidata_db.py)"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API  = "https://www.wikidata.org/w/api.php"
CACHE_DIR     = "data/wikidata_cache"
BATCH_SIZE    = 50
SLEEP_BETWEEN = 1.5
REQUEST_TIMEOUT = 30

# Same property set as build_fever_wikidata.py — must stay in sync.
PROPERTIES = [
    # Geography
    'P17', 'P36', 'P1376', 'P131', 'P30', 'P610', 'P2044', 'P2046',
    'P47', 'P206', 'P190', 'P276', 'P159',
    # People
    'P569', 'P570', 'P19', 'P20', 'P27', 'P106', 'P108', 'P39',
    'P69', 'P26', 'P22', 'P25', 'P40', 'P1037', 'P169',
    # Organizations
    'P355', 'P127', 'P176', 'P1001',
    # Media / taxonomy
    'P31', 'P279', 'P171', 'P161', 'P57', 'P162', 'P86', 'P175',
    'P264', 'P136', 'P179', 'P495', 'P449', 'P465', 'P50', 'P170',
    'P800', 'P1441', 'P361', 'P527',
    # Sports
    'P54', 'P118', 'P413', 'P1344',
    # Language / culture
    'P37', 'P38', 'P407', 'P364', 'P1412', 'P135', 'P166',
    # Time
    'P571', 'P580', 'P582', 'P585', 'P577',
    # Succession
    'P155', 'P156',
]


# ── Claim loading ─────────────────────────────────────────────────────────────

def load_claims(path: str):
    claims = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                claims.append(json.loads(line))
    return claims


# ── Entity extraction from claim text ────────────────────────────────────────

def _strip_compound_np(name: str) -> list:
    """Return candidate entity names derived from a complex NP.

    Handles:
      "Sensitive Skin's first series"  → ["Sensitive Skin"]
      "The area of Muş Province"       → ["Muş Province"]
      "a movie called Inception"       → ["Inception"]
      "the city of Paris"              → ["Paris"]
      "members of Congress"            → ["Congress"]
    """
    candidates = [name]
    n = name.strip()

    # Possessive: "X's Y" → try "X"
    m = re.match(r"^(.+?)'s\b", n, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).strip())

    # "area of X", "city of X", "member of X", etc.
    m = re.match(r'^(?:the\s+)?(?:\w+\s+){0,2}of\s+(.+)$', n, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).strip())

    # "a/an [type] called/named X"
    m = re.match(r'^(?:a|an|the)\s+\w[\w\s,]+\s+(?:called|named)\s+(.+)$', n, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).strip())

    # Strip leading article
    for art in ('the ', 'a ', 'an '):
        stripped = re.sub(r'^' + art, '', n, flags=re.IGNORECASE).strip()
        if stripped and stripped != n:
            candidates.append(stripped)

    return list(dict.fromkeys(candidates))  # preserve order, unique


def extract_entity_names_from_claims(claims: list) -> set:
    """Extract candidate entity names from all claims using spaCy NER
    and ClaimExtractor triples.

    Returns a set of candidate entity name strings.
    """
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        have_spacy = True
    except Exception:
        nlp = None
        have_spacy = False
        print("  [warn] spaCy not available — NER pass skipped")

    try:
        from src.extraction.claim_extractor import ClaimExtractor
        extractor = ClaimExtractor()
        have_extractor = True
    except Exception:
        extractor = None
        have_extractor = False
        print("  [warn] ClaimExtractor not available — triple pass skipped")

    names = set()

    for item in claims:
        text = item.get("claim", "")
        if not text:
            continue

        # NER pass
        if have_spacy:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ in {"PERSON", "ORG", "GPE", "LOC", "WORK_OF_ART",
                                  "EVENT", "FAC", "PRODUCT", "LAW", "NORP"}:
                    raw = ent.text.strip()
                    for candidate in _strip_compound_np(raw):
                        if len(candidate) > 1:
                            names.add(candidate)

        # Triple-extraction pass
        if have_extractor:
            try:
                result = extractor.extract(text)
                for claim in result.claims:
                    for part in (claim.subject, claim.object):
                        if not part:
                            continue
                        for candidate in _strip_compound_np(part.strip()):
                            if len(candidate) > 2:
                                names.add(candidate)
            except Exception:
                pass

    return names


# ── Filtering: skip entities already well-covered in DB ──────────────────────

def filter_already_present(names: set, db_path: str) -> set:
    """Remove names that already resolve to entities WITH claims in the DB."""
    if not os.path.exists(db_path):
        return names
    conn = sqlite3.connect(db_path)
    missing = set()
    for name in names:
        name_lower = name.lower().strip()
        row = conn.execute(
            "SELECT qid FROM entities WHERE label_lower = ? OR qid IN "
            "(SELECT qid FROM aliases WHERE alias_lower = ?) LIMIT 1",
            (name_lower, name_lower)
        ).fetchone()
        if not row:
            missing.add(name)
        else:
            qid = row[0]
            # Present but may have no claims (referenced-only entity)
            n_claims = conn.execute(
                "SELECT COUNT(*) FROM claims WHERE qid = ?", (qid,)
            ).fetchone()[0]
            if n_claims == 0:
                missing.add(name)
    conn.close()
    print(f"  {len(names) - len(missing)} names already in DB with claims → skipping")
    return missing


# ── Wikipedia → Wikidata resolution ──────────────────────────────────────────

def _cache_path(url, params):
    sorted_params = sorted(params.items())
    key_str = url + "?" + urllib.parse.urlencode(sorted_params)
    key_hash = hashlib.md5(key_str.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key_hash}.json")


def api_get(url, params, retries=3):
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    cpath = _cache_path(url, params)
    if os.path.exists(cpath):
        with open(cpath) as f:
            return json.load(f)
    for attempt in range(retries):
        try:
            query = urllib.parse.urlencode(params)
            req = urllib.request.Request(
                f"{url}?{query}", headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                with open(cpath, "w") as f:
                    json.dump(data, f)
                return data
        except urllib.error.HTTPError as e:
            if e.code in (429,) or e.code >= 500:
                wait = 2 ** (attempt + 1)
                print(f"    HTTP {e.code}, retry in {wait}s...")
                time.sleep(wait)
            else:
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                print(f"    Failed: {e}")
                return None
    return None


def resolve_names(names: set, max_entities=None):
    """Resolve entity name strings → Wikidata QIDs via Wikipedia API.

    Uses the Wikipedia opensearch + pageprops pipeline:
      name → Wikipedia title → QID
    """
    name_list = sorted(names)
    if max_entities:
        name_list = name_list[:max_entities]

    qid_map = {}   # name → qid
    unresolved = set()

    # Batch: Wikipedia pageprops (wikibase_item) for exact title matches
    for i in range(0, len(name_list), BATCH_SIZE):
        batch = name_list[i: i + BATCH_SIZE]
        params = {
            "action": "query",
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "titles": "|".join(batch),
            "redirects": "1",
            "format": "json",
        }
        data = api_get(WIKIPEDIA_API, params)
        time.sleep(SLEEP_BETWEEN)

        if not data or "query" not in data:
            unresolved.update(batch)
            continue

        q = data["query"]
        norm_map  = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir_map = {r["from"]: r["to"] for r in q.get("redirects",  [])}
        page_qids = {}
        for page in q.get("pages", {}).values():
            if "missing" in page:
                continue
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                page_qids[page.get("title", "")] = qid

        for name in batch:
            step1 = norm_map.get(name, name)
            step2 = redir_map.get(step1, step1)
            if step2 in page_qids:
                qid_map[name] = page_qids[step2]
            else:
                unresolved.add(name)

        done = min(i + BATCH_SIZE, len(name_list))
        print(f"  Resolved {len(qid_map)}/{done} via pageprops "
              f"({len(unresolved)} unresolved)")

    # Fallback: Wikipedia opensearch for unresolved names
    still_unresolved = set()
    opensearch_resolved = {}
    for name in unresolved:
        params = {
            "action": "opensearch",
            "search": name,
            "limit": 1,
            "redirects": "resolve",
            "format": "json",
        }
        data = api_get(WIKIPEDIA_API, params)
        time.sleep(0.5)
        if data and len(data) >= 2 and data[1]:
            title = data[1][0]
            # Now get the QID for that title
            pp_params = {
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "titles": title,
                "format": "json",
            }
            pp_data = api_get(WIKIPEDIA_API, pp_params)
            if pp_data and "query" in pp_data:
                for page in pp_data["query"].get("pages", {}).values():
                    qid = page.get("pageprops", {}).get("wikibase_item")
                    if qid:
                        opensearch_resolved[name] = qid
                        break
        if name not in opensearch_resolved:
            still_unresolved.add(name)

    if opensearch_resolved:
        print(f"  Opensearch fallback resolved {len(opensearch_resolved)} more names")
    qid_map.update(opensearch_resolved)

    return qid_map, still_unresolved


# ── Entity data fetching ─────────────────────────────────────────────────────

def fetch_entities(qids: set) -> dict:
    """Fetch labels, aliases, and filtered claims for a set of QIDs."""
    entities = {}
    qid_list = sorted(qids)

    for i in range(0, len(qid_list), BATCH_SIZE):
        batch = qid_list[i: i + BATCH_SIZE]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels|aliases|claims",
            "languages": "en",
            "format": "json",
        }
        data = api_get(WIKIDATA_API, params)
        time.sleep(SLEEP_BETWEEN)

        if not data or "entities" not in data:
            continue

        for qid, entity in data["entities"].items():
            if "missing" in entity:
                continue
            en_label = entity.get("labels", {}).get("en", {}).get("value", qid)
            aliases = [a.get("value", "")
                       for a in entity.get("aliases", {}).get("en", [])]
            raw_claims = entity.get("claims", {})
            filtered = {p: raw_claims[p] for p in PROPERTIES if p in raw_claims}
            entities[qid] = {
                "label": en_label, "aliases": aliases, "claims": filtered
            }

        done = min(i + BATCH_SIZE, len(qid_list))
        print(f"  Fetched entities: {len(entities)}/{done}")

    return entities


def fetch_labels(qids: set) -> dict:
    """Fetch only English labels for referenced QIDs."""
    label_map = {}
    qid_list = sorted(qids)

    for i in range(0, len(qid_list), BATCH_SIZE):
        batch = qid_list[i: i + BATCH_SIZE]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "en",
            "format": "json",
        }
        data = api_get(WIKIDATA_API, params)
        time.sleep(SLEEP_BETWEEN)

        if not data or "entities" not in data:
            continue

        for qid, entity in data["entities"].items():
            if "missing" in entity:
                label_map[qid] = qid
            else:
                label_map[qid] = (
                    entity.get("labels", {}).get("en", {}).get("value", qid)
                )

        done = min(i + BATCH_SIZE, len(qid_list))
        print(f"  Fetched labels: {len(label_map)}/{done}")

    return label_map


# ── Claim value formatting ────────────────────────────────────────────────────

def _format_time(time_str, precision):
    t = time_str.lstrip("+")
    if precision >= 11:
        return t[:10]
    elif precision == 10:
        return t[:7]
    else:
        return t[:4]


def format_claim_value(snak, label_map):
    if snak.get("snaktype") != "value":
        return None
    dv   = snak.get("datavalue", {})
    dvt  = dv.get("type")
    val  = dv.get("value", {})

    if dvt in ("wikibase-item", "wikibase-entityid"):
        qid   = val.get("id") or f"Q{val.get('numeric-id')}"
        label = label_map.get(qid, qid)
        return label, qid
    elif dvt == "time":
        return _format_time(val.get("time", ""), val.get("precision", 11)), None
    elif dvt == "quantity":
        return str(val.get("amount", "")).lstrip("+"), None
    elif dvt == "string":
        return val, None
    elif dvt == "monolingualtext":
        return val.get("text", ""), None
    elif dvt == "globecoordinate":
        return f"{val.get('latitude',0)},{val.get('longitude',0)}", None
    return None


# ── Database augmentation ─────────────────────────────────────────────────────

def augment_database(db_path: str, entities_data: dict, label_map: dict) -> dict:
    """INSERT OR REPLACE new entities into an existing DB.

    Skips entities that already have claims to avoid redundant work.
    """
    conn = sqlite3.connect(db_path)

    before_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    before_claims   = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    before_aliases  = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]

    existing_qids_with_claims = set(
        row[0] for row in conn.execute(
            "SELECT DISTINCT qid FROM claims"
        ).fetchall()
    )

    new_entities = 0
    new_claims   = 0
    new_aliases  = 0

    for qid, data in entities_data.items():
        label = data["label"]
        conn.execute(
            "INSERT OR REPLACE INTO entities "
            "(qid, label, label_lower, description) VALUES (?, ?, ?, ?)",
            (qid, label, label.lower(), "from claim-text extension")
        )
        new_entities += 1

        for alias in data["aliases"]:
            # Avoid duplicate aliases
            exists = conn.execute(
                "SELECT 1 FROM aliases WHERE qid=? AND alias_lower=?",
                (qid, alias.lower())
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO aliases (qid, alias_lower) VALUES (?, ?)",
                    (qid, alias.lower())
                )
                new_aliases += 1

        if qid in existing_qids_with_claims:
            # Already has claims — skip to avoid duplicate claim rows.
            # Labels/aliases have been refreshed above.
            continue

        for prop, claim_list in data["claims"].items():
            for claim in claim_list:
                if claim.get("rank") == "deprecated":
                    continue
                snak = claim.get("mainsnak", {})
                formatted = format_claim_value(snak, label_map)
                if formatted:
                    value_str, value_qid = formatted
                    conn.execute(
                        "INSERT INTO claims (qid, property, value, value_qid) "
                        "VALUES (?, ?, ?, ?)",
                        (qid, prop, value_str, value_qid)
                    )
                    new_claims += 1

    # Add referenced entities (labels only)
    main_qids = set(entities_data.keys())
    for qid, label in label_map.items():
        if qid not in main_qids:
            conn.execute(
                "INSERT OR REPLACE INTO entities "
                "(qid, label, label_lower, description) VALUES (?, ?, ?, ?)",
                (qid, label, label.lower(), "referenced entity")
            )

    conn.commit()

    after_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    after_claims   = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    after_aliases  = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    db_size_kb     = os.path.getsize(db_path) / 1024
    conn.close()

    return {
        "entities_added":   after_entities - before_entities,
        "claims_added":     after_claims   - before_claims,
        "aliases_added":    after_aliases  - before_aliases,
        "total_entities":   after_entities,
        "total_claims":     after_claims,
        "db_size_kb":       db_size_kb,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extend an existing Wikidata DB with claim-text entities"
    )
    parser.add_argument("--claims", default="data/fever2_oracle_sample.jsonl",
                        help="FEVER-style JSONL claim file (default: oracle sample)")
    parser.add_argument("--db-path", default="data/wikidata_fever.db",
                        help="Existing SQLite DB to augment")
    parser.add_argument("--max-entities", type=int, default=None,
                        help="Cap on new entities to fetch (useful for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print candidate entity names without fetching")
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"ERROR: DB not found at {args.db_path}. "
              f"Run build_fever_wikidata.py first.")
        sys.exit(1)

    print(f"Loading claims from {args.claims} ...")
    claims = load_claims(args.claims)
    print(f"  Loaded {len(claims)} claims.")

    print(f"\nExtracting entity names from claim text ...")
    names = extract_entity_names_from_claims(claims)
    print(f"  {len(names)} candidate entity names extracted.")

    print(f"\nFiltering out names already well-covered in DB ...")
    names = filter_already_present(names, args.db_path)
    print(f"  {len(names)} names need fetching.")

    if args.dry_run:
        print("\n=== DRY RUN: candidate entity names ===")
        for n in sorted(names)[:200]:
            print(f"  {n}")
        if len(names) > 200:
            print(f"  ... and {len(names)-200} more")
        return

    if not names:
        print("Nothing to fetch — DB is already up to date.")
        return

    print(f"\nResolving {len(names)} entity names → Wikidata QIDs ...")
    qid_map, unresolved = resolve_names(names, max_entities=args.max_entities)
    print(f"  Resolved {len(qid_map)}/{len(names)}; {len(unresolved)} unresolved")

    if not qid_map:
        print("No QIDs resolved. Check network connectivity.")
        sys.exit(1)

    print(f"\nFetching Wikidata entity data for {len(qid_map)} QIDs ...")
    new_qids = set(qid_map.values())
    entities_data = fetch_entities(new_qids)
    print(f"  Fetched {len(entities_data)} entities.")

    print(f"\nResolving labels for referenced entities ...")
    referenced_qids = set()
    for data in entities_data.values():
        for prop_claims in data["claims"].values():
            for claim in prop_claims:
                snak = claim.get("mainsnak", {})
                dv   = snak.get("datavalue", {})
                if dv.get("type") in ("wikibase-item", "wikibase-entityid"):
                    v    = dv.get("value", {})
                    rqid = v.get("id") or f"Q{v.get('numeric-id')}"
                    if rqid and rqid not in entities_data:
                        referenced_qids.add(rqid)

    print(f"  {len(referenced_qids)} referenced QIDs need labels.")
    ref_labels = fetch_labels(referenced_qids) if referenced_qids else {}

    label_map = {qid: data["label"] for qid, data in entities_data.items()}
    label_map.update(ref_labels)

    print(f"\nAugmenting database: {args.db_path}")
    stats = augment_database(args.db_path, entities_data, label_map)

    print(f"\n{'='*60}")
    print(f"  Claims processed:         {len(claims)}")
    print(f"  Entity names extracted:   {len(names) + (len(names) - len(names))}")
    print(f"  Names resolved to QIDs:   {len(qid_map)}")
    print(f"  Entities fetched:         {len(entities_data)}")
    print(f"  Entities added to DB:     {stats['entities_added']}")
    print(f"  Claims added to DB:       {stats['claims_added']}")
    print(f"  Aliases added to DB:      {stats['aliases_added']}")
    print(f"  Total entities in DB:     {stats['total_entities']}")
    print(f"  Total claims in DB:       {stats['total_claims']}")
    print(f"  DB size:                  {stats['db_size_kb']:.1f} KB")
    print(f"{'='*60}")
    print(f"\nDone. Re-run the eval script to see coverage improvement:")
    print(f"  python scripts/eval_fever2.py \\")
    print(f"    --db-path {args.db_path} \\")
    print(f"    --sample-path {args.claims} \\")
    print(f"    --output-suffix oracle")


if __name__ == "__main__":
    main()

