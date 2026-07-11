#!/usr/bin/env python3
"""Build a FEVER-targeted Wikidata database (oracle coverage).

Downloads Wikidata entities for the specific Wikipedia pages referenced in
FEVER 2.0 evidence annotations. This provides oracle coverage — the
verifier has access to exactly the entities needed for each claim — to
isolate the effect of database coverage from verifier logic.

This is a DIAGNOSTIC database, not operational: in real deployment the
system would not have access to gold evidence annotations.

Usage:
    python scripts/build_fever_wikidata.py                    # 100/class (300 total)
    python scripts/build_fever_wikidata.py --n-per-class 0     # all 1174 claims
    python scripts/build_fever_wikidata.py --max-entities 20  # quick test

Outputs:
    data/wikidata_fever.db                  — SQLite DB (same schema as wikidata_seed.db)
    data/fever2_oracle_sample.jsonl         — the claims used (for eval script)
    evaluation_results/fever2_db_build.json — build stats

Requires: stdlib only (urllib, sqlite3, json). Internet access to Wikipedia + Wikidata.
"""
import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Configuration ───────────────────────────────────────────────────────────
FEVER2_PATH = "fever/fever2/fever2-fixers-dev.jsonl"
OUTPUT_DB = "data/wikidata_fever.db"
OUTPUT_CLAIMS = "data/fever2_oracle_sample.jsonl"
OUTPUT_STATS = "evaluation_results/fever2_db_build.json"

USER_AGENT = "FEVER-Eval-Research/1.0 (academic research; build_fever_wikidata.py)"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

BATCH_SIZE = 50
SLEEP_BETWEEN = 1.5
REQUEST_TIMEOUT = 30

# Disk cache for API responses — survives across runs so 429'd batches
# can be retried without re-downloading everything that succeeded.
CACHE_DIR = "data/wikidata_cache"

# Properties to extract (must align with wikidata_offline.py PREDICATE_TO_PROPERTY)
# Expanded to cover FEVER 2.0 entity types: films, TV, music, sports, taxonomy,
# people, organizations, and places.
PROPERTIES = [
    # ── Geography (original) ──
    'P17',    # country
    'P36',    # capital
    'P1376',  # capital of
    'P131',   # located in administrative entity
    'P30',    # continent
    'P610',   # highest point
    'P2044',  # elevation
    'P2046',  # area
    'P47',    # shares border with
    'P206',   # body of water
    'P190',   # twin city
    'P276',   # location
    'P159',   # seat of government
    # ── People: life events ──
    'P569',   # date of birth
    'P570',   # date of death
    'P19',    # place of birth
    'P20',    # place of death
    'P27',    # citizenship
    'P106',   # occupation
    'P108',   # employer
    'P39',    # position held
    'P69',    # educated at
    'P26',    # spouse
    'P22',    # father
    'P25',    # mother
    'P40',    # child
    'P1037',  # chairperson
    'P169',   # chief executive officer
    # ── Organizations / business ──
    'P355',   # subsidiary
    'P127',   # owned by
    'P176',   # manufacturer
    'P1001',  # applies to jurisdiction
    # ── Media: film / TV ──
    'P31',    # instance of  ← critical: "X is a cat/country/person"
    'P279',   # subclass of  ← critical: taxonomy "X includes Y"
    'P171',   # parent taxon ← critical: taxonomy
    'P161',   # cast member
    'P57',    # director
    'P162',   # producer
    'P86',    # composer
    'P175',   # performer
    'P264',   # record label
    'P136',   # genre
    'P179',   # part of series
    'P495',   # country of origin
    'P449',   # original broadcaster
    'P465',   # production company
    'P50',    # author
    'P170',   # creator
    'P800',   # notable work
    'P1441',  # present in work
    'P361',   # part of  ← "member of", "part of a series"
    'P527',   # has part(s) ← "includes"
    # ── Sports ──
    'P54',    # member of sports team
    'P118',   # sport
    'P413',   # position played
    'P1344',  # participant in
    # ── Language / culture ──
    'P37',    # official language
    'P38',    # currency
    'P407',   # language of work
    'P364',   # original language
    'P1412',  # languages spoken
    'P135',   # movement
    'P166',   # award received
    # ── Time (original) ──
    'P571',   # inception
    'P580',   # start time
    'P582',   # end time
    'P585',   # point in time
    'P577',   # publication date  ← debut / release date
    # ── Succession ──
    'P155',   # follows
    'P156',   # followed by
    # ── Naming ──
    'P1449',  # nickname
    'P1476',  # title
]

# ── Schema (identical to build_wikidata_db.py) ─────────────────────────────
SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS entities (
        qid TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        label_lower TEXT NOT NULL,
        description TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS aliases (
        qid TEXT NOT NULL,
        alias_lower TEXT NOT NULL,
        FOREIGN KEY (qid) REFERENCES entities(qid)
    );
    CREATE TABLE IF NOT EXISTS claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qid TEXT NOT NULL,
        property TEXT NOT NULL,
        value TEXT NOT NULL,
        value_qid TEXT DEFAULT NULL,
        FOREIGN KEY (qid) REFERENCES entities(qid)
    );
    CREATE INDEX IF NOT EXISTS idx_entities_label_lower ON entities(label_lower);
    CREATE INDEX IF NOT EXISTS idx_aliases_alias_lower ON aliases(alias_lower);
    CREATE INDEX IF NOT EXISTS idx_claims_qid ON claims(qid);
    CREATE INDEX IF NOT EXISTS idx_claims_qid_property ON claims(qid, property);
"""

# ── Label normalization ──────────────────────────────────────────────────────
_LABEL_MAP = {
    "supports": "SUPPORTS",
    "refutes": "REFUTES",
    "refuted": "REFUTES",
    "not enough info": "NOT ENOUGH INFO",
}


def normalize_label(raw):
    return _LABEL_MAP.get(raw.strip().lower(), raw.strip().upper())


# ── FEVER loading ────────────────────────────────────────────────────────────
def load_fever2(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not obj.get("label") or not obj.get("claim"):
                continue
            obj["label"] = normalize_label(obj["label"])
            rows.append(obj)
    return rows


def select_claims(rows, n_per_class, seed=42):
    if n_per_class <= 0:
        print(f"  Using ALL {len(rows)} claims")
        return rows
    by_label = defaultdict(list)
    for r in rows:
        by_label[r["label"]].append(r)
    rng = random.Random(seed)
    sample = []
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        pool = by_label.get(label, [])
        rng.shuffle(pool)
        taken = pool[:n_per_class]
        sample.extend(taken)
        print(f"  {label}: {len(taken)} sampled (of {len(pool)} available)")
    return sample


def clean_fever_title(title):
    """Decode FEVER's Wikipedia title encoding to plain text."""
    title = title.replace("-LRB-", "(").replace("-RRB-", ")")
    title = title.replace("-LSB-", "[").replace("-RSB-", "]")
    title = title.replace("-COLON-", ":")
    title = title.replace("_", " ")
    return title.strip()


def extract_titles(claims):
    """Extract unique Wikipedia page titles from FEVER evidence annotations."""
    titles = set()
    for claim_obj in claims:
        for evidence_set in claim_obj.get("evidence", []):
            if not isinstance(evidence_set, list):
                continue
            for ev in evidence_set:
                if not isinstance(ev, list) or len(ev) < 3:
                    continue
                title = ev[2]
                if title and isinstance(title, str) and title.strip():
                    titles.add(title.strip())
    return titles


# ── API calls with disk caching ────────────────────────────────────────────
def _cache_path(url, params):
    """Generate a deterministic cache file path from request URL + params."""
    sorted_params = sorted(params.items())
    key_str = url + "?" + urllib.parse.urlencode(sorted_params)
    key_hash = hashlib.md5(key_str.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key_hash}.json")


def api_get(url, params, retries=3):
    """Fetch from API with disk caching.

    On first call: make the HTTP request and cache the response.
    On subsequent calls: load from cache (instant, no network).
    Failed requests (429, timeout) are NOT cached so they get retried on re-run.
    """
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    cpath = _cache_path(url, params)

    # Cache hit — return instantly
    if os.path.exists(cpath):
        with open(cpath, "r") as f:
            return json.load(f)

    # Cache miss — make the request
    for attempt in range(retries):
        try:
            query = urllib.parse.urlencode(params)
            full_url = f"{url}?{query}"
            req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                # Save successful response to cache
                with open(cpath, "w") as f:
                    json.dump(data, f)
                return data
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = 2 ** (attempt + 1)
                print(f"    HTTP {e.code}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"    HTTP error {e.code}: {e.reason}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    Error: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"    Failed after {retries} retries: {e}")
                return None
    return None


def resolve_titles(titles, max_entities=None):
    """Resolve Wikipedia page titles to Wikidata QIDs (batched 50)."""
    title_list = sorted(titles)
    if max_entities:
        title_list = title_list[:max_entities]

    qid_map = {}
    unresolved = set()

    for i in range(0, len(title_list), BATCH_SIZE):
        batch = title_list[i:i + BATCH_SIZE]
        cleaned = [clean_fever_title(t) for t in batch]
        params = {
            "action": "query",
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "titles": "|".join(cleaned),
            "redirects": "1",
            "format": "json",
        }
        data = api_get(WIKIPEDIA_API, params)
        time.sleep(SLEEP_BETWEEN)

        if not data or "query" not in data:
            unresolved.update(batch)
            continue

        query = data["query"]
        norm_map = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redir_map = {r["from"]: r["to"] for r in query.get("redirects", [])}

        page_qids = {}
        for page in query.get("pages", {}).values():
            if "missing" in page:
                continue
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                page_qids[page.get("title", "")] = qid

        for orig, clean in zip(batch, cleaned):
            step1 = norm_map.get(clean, clean)
            step2 = redir_map.get(step1, step1)
            if step2 in page_qids:
                qid_map[orig] = page_qids[step2]
            else:
                unresolved.add(orig)

        done = min(i + BATCH_SIZE, len(title_list))
        print(f"  Resolved: {len(qid_map)}/{done} ({len(unresolved)} unresolved)")

    return qid_map, unresolved


def fetch_entities(qids):
    """Fetch labels, aliases, and filtered claims for a set of QIDs."""
    entities = {}
    qid_list = sorted(qids)

    for i in range(0, len(qid_list), BATCH_SIZE):
        batch = qid_list[i:i + BATCH_SIZE]
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
            aliases = [a.get("value", "") for a in entity.get("aliases", {}).get("en", [])]
            raw_claims = entity.get("claims", {})
            filtered = {p: raw_claims[p] for p in PROPERTIES if p in raw_claims}
            entities[qid] = {"label": en_label, "aliases": aliases, "claims": filtered}

        done = min(i + BATCH_SIZE, len(qid_list))
        print(f"  Fetched entities: {len(entities)}/{done}")

    return entities


def fetch_labels(qids):
    """Fetch only English labels for a set of QIDs (for referenced entities)."""
    label_map = {}
    qid_list = sorted(qids)

    for i in range(0, len(qid_list), BATCH_SIZE):
        batch = qid_list[i:i + BATCH_SIZE]
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
                continue
            label_map[qid] = entity.get("labels", {}).get("en", {}).get("value", qid)

        done = min(i + BATCH_SIZE, len(qid_list))
        print(f"  Fetched labels: {len(label_map)}/{done}")

    return label_map


# ── Claim value formatting ──────────────────────────────────────────────────
def format_time(time_str, precision):
    t = time_str.lstrip("+")
    if precision >= 11:
        return t[:10]
    elif precision == 10:
        return t[:7]
    else:
        return t[:4]


def format_claim_value(snak, label_map):
    """Extract (value_str, value_qid) from a claim mainsnak, or None.

    NOTE: The wbgetentities API returns item references with datavalue type
    "wikibase-entityid" (NOT "wikibase-item", which is the dump format).
    Both are accepted here so entity-typed properties (P31, P17, P36, P27,
    P106, P161, P54, ...) are captured instead of silently dropped.
    """
    if snak.get("snaktype") != "value":
        return None
    dv = snak.get("datavalue", {})
    dv_type = dv.get("type")
    value = dv.get("value", {})

    if dv_type in ("wikibase-item", "wikibase-entityid"):
        qid = value.get("id") or f"Q{value.get('numeric-id')}"
        label = label_map.get(qid, qid)
        return label, qid
    elif dv_type == "time":
        return format_time(value.get("time", ""), value.get("precision", 11)), None
    elif dv_type == "quantity":
        return str(value.get("amount", "")).lstrip("+"), None
    elif dv_type == "string":
        return value, None
    elif dv_type == "monolingualtext":
        return value.get("text", ""), None
    elif dv_type == "globecoordinate":
        return f"{value.get('latitude',0)},{value.get('longitude',0)}", None
    else:
        return None


# ── Database building ───────────────────────────────────────────────────────
def build_database(db_path, entities_data, label_map):
    if os.path.exists(db_path):
        os.remove(db_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    for qid, data in entities_data.items():
        label = data["label"]
        conn.execute(
            "INSERT OR REPLACE INTO entities (qid, label, label_lower, description) "
            "VALUES (?, ?, ?, ?)",
            (qid, label, label.lower(), "from FEVER evidence")
        )
        for alias in data["aliases"]:
            conn.execute(
                "INSERT INTO aliases (qid, alias_lower) VALUES (?, ?)",
                (qid, alias.lower())
            )
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

    main_qids = set(entities_data.keys())
    for qid, label in label_map.items():
        if qid not in main_qids:
            conn.execute(
                "INSERT OR REPLACE INTO entities (qid, label, label_lower, description) "
                "VALUES (?, ?, ?, ?)",
                (qid, label, label.lower(), "referenced entity")
            )

    conn.commit()
    stats = {
        "main_entities": len(main_qids),
        "referenced_entities": len(label_map) - len(main_qids),
        "total_entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "aliases": conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        "claims": conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
        "size_kb": os.path.getsize(db_path) / 1024,
    }
    conn.close()
    return stats


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Build FEVER-targeted Wikidata DB (oracle coverage)"
    )
    parser.add_argument("--n-per-class", type=int, default=100,
                        help="FEVER claims per class (0 = all, default 100)")
    parser.add_argument("--max-entities", type=int, default=None,
                        help="Cap on entities to download (for quick testing)")
    parser.add_argument("--output", default=OUTPUT_DB,
                        help="Output SQLite path (default: data/wikidata_fever.db)")
    parser.add_argument(
        "--extend-from-claims", metavar="JSONL",
        help="After building the base DB, also run the claim-text extension "
             "pass (equivalent to calling extend_wikidata_db.py --claims JSONL). "
             "Adds entities extracted via NER and triple extraction from claim text."
    )
    args = parser.parse_args()

    db_path = args.output
    start_time = time.time()

    # Phase 1: Load FEVER and select claims (same seed as eval script)
    print(f"Loading FEVER 2.0 from {FEVER2_PATH} ...")
    rows = load_fever2(FEVER2_PATH)
    print(f"Loaded {len(rows)} claims. Selecting:")
    claims = select_claims(rows, args.n_per_class)
    print(f"Selected {len(claims)} claims.")

    Path(OUTPUT_CLAIMS).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CLAIMS, "w") as f:
        for row in claims:
            f.write(json.dumps(row) + "\n")
    print(f"Saved selected claims to {OUTPUT_CLAIMS}")

    # Phase 2: Extract entity titles from evidence annotations
    titles = extract_titles(claims)
    print(f"\nExtracted {len(titles)} unique Wikipedia page titles from evidence.")

    # Phase 3: Resolve titles to Wikidata QIDs
    print(f"\nResolving titles to Wikidata QIDs (batches of {BATCH_SIZE}) ...")
    qid_map, unresolved = resolve_titles(titles, max_entities=args.max_entities)
    resolution_rate = len(qid_map) / len(titles) if titles else 0
    print(f"Resolved {len(qid_map)}/{len(titles)} titles ({resolution_rate*100:.1f}%)")
    if unresolved:
        print(f"  {len(unresolved)} titles unresolved")

    if not qid_map:
        print("\nERROR: No titles resolved. Check network connectivity.")
        sys.exit(1)

    # Phase 4: Fetch entity data
    print(f"\nFetching Wikidata entities (batches of {BATCH_SIZE}) ...")
    entities_data = fetch_entities(set(qid_map.values()))
    print(f"Fetched {len(entities_data)} entities.")

    # Phase 5: Collect referenced QIDs and resolve their labels
    # NOTE: same wikibase-entityid type check as format_claim_value — without it
    # the referenced-QID scan finds zero and item-typed claim values are stored
    # as raw QIDs instead of labels.
    print(f"\nResolving labels for referenced entities ...")
    referenced_qids = set()
    for qid, data in entities_data.items():
        for prop, claim_list in data["claims"].items():
            for claim in claim_list:
                snak = claim.get("mainsnak", {})
                dv = snak.get("datavalue", {})
                if dv.get("type") in ("wikibase-item", "wikibase-entityid"):
                    val = dv.get("value", {})
                    ref_qid = val.get("id") or f"Q{val.get('numeric-id')}"
                    if ref_qid and ref_qid not in entities_data:
                        referenced_qids.add(ref_qid)

    print(f"  {len(referenced_qids)} referenced QIDs need label resolution.")
    ref_labels = fetch_labels(referenced_qids) if referenced_qids else {}

    label_map = {qid: data["label"] for qid, data in entities_data.items()}
    label_map.update(ref_labels)
    print(f"  Label map: {len(label_map)} total entities.")

    # Phase 6: Build database
    print(f"\nBuilding database: {db_path}")
    stats = build_database(db_path, entities_data, label_map)

    elapsed = time.time() - start_time

    # Phase 7: Summary
    print(f"\n{'='*60}")
    print(f"  FEVER claims processed:    {len(claims)}")
    print(f"  Unique titles extracted:   {len(titles)}")
    print(f"  Titles resolved to QIDs:   {len(qid_map)} ({resolution_rate*100:.1f}%)")
    print(f"  Entities fetched:          {stats['main_entities']}")
    print(f"  Referenced entities added:  {stats['referenced_entities']}")
    print(f"  Total entities in DB:      {stats['total_entities']}")
    print(f"  Aliases:                   {stats['aliases']}")
    print(f"  Claims (filtered):         {stats['claims']}")
    print(f"  Database size:              {stats['size_kb']:.1f} KB")
    print(f"  Time elapsed:               {elapsed:.1f}s")
    print(f"{'='*60}")

    build_stats = {
        "fever_claims": len(claims),
        "n_per_class": args.n_per_class,
        "titles_extracted": len(titles),
        "titles_resolved": len(qid_map),
        "resolution_rate": resolution_rate,
        "unresolved_titles": len(unresolved),
        "entities_fetched": stats["main_entities"],
        "referenced_entities": stats["referenced_entities"],
        "total_entities": stats["total_entities"],
        "aliases": stats["aliases"],
        "claims": stats["claims"],
        "db_size_kb": stats["size_kb"],
        "db_path": db_path,
        "elapsed_seconds": elapsed,
        "note": ("Oracle coverage DB built from FEVER evidence annotations. "
                 "Diagnostic only — not operational."),
    }
    os.makedirs(os.path.dirname(OUTPUT_STATS) or ".", exist_ok=True)
    with open(OUTPUT_STATS, "w") as f:
        json.dump(build_stats, f, indent=2)
    print(f"\nSaved build stats: {OUTPUT_STATS}")
    print(f"\nDatabase ready: {db_path}")
    print(f"Run eval with:")
    print(f"  python scripts/eval_fever2.py \\")
    print(f"    --db-path {db_path} \\")
    print(f"    --sample-path {OUTPUT_CLAIMS} \\")
    print(f"    --output-suffix oracle")

    # Optional second pass: extend from claim text entities
    if args.extend_from_claims:
        extend_path = args.extend_from_claims
        print(f"\n{'='*60}")
        print(f"Running claim-text extension from {extend_path} ...")
        import subprocess
        extend_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "extend_wikidata_db.py"
        )
        cmd = [
            sys.executable, extend_script,
            "--claims", extend_path,
            "--db-path", db_path,
        ]
        if args.max_entities:
            cmd += ["--max-entities", str(args.max_entities)]
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()