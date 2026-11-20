#!/usr/bin/env python3
"""Fetch a Wikidata KB slice for the 93-statement USA true/false set.

Builds ``data/wikidata_usa_93.db`` from ``data/wikidata_seed.db`` plus
fresh Wikidata fetches for the entities the 93 statements mention. Existing
seed entities (the USA, Congress, the Senate, the House, the Constitution,
Washington, D.C., ...) are refreshed so the dataset's properties are present;
new entities (the Supreme Court, the Bill of Rights, Alaska, California,
Chicago, ...) are added.

The shipped ``data/wikidata_seed.db`` is never modified. The target DB is a
copy, so the default pipeline keeps its 144-entity behaviour until a caller
passes ``db_path`` (``OfflineWikidata(db_path=...)`` /
``Prong3Extraction(wikidata_db_path=...)``).

Usage:
    python scripts/fetch_usa_93_kb.py
    python scripts/fetch_usa_93_kb.py --dry-run
    python scripts/fetch_usa_93_kb.py --target data/wikidata_usa_93.db

Network: Wikipedia pageprops/opensearch for name -> QID resolution, then the
Wikidata ``wbgetentities`` API for labels, aliases, and filtered claims.
Responses are cached under ``data/wikidata_cache``. The manifest at
``data/wikidata_usa_93_manifest.json`` records the name -> QID mapping, the
property list, and the counts, so the slice can be audited later.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

import extend_wikidata_db as ext  # noqa: E402

DATASET = os.path.join(ROOT, "data", "usa_true_false_clean.json")
SEED_DB = os.path.join(ROOT, "data", "wikidata_seed.db")
DEFAULT_TARGET = os.path.join(ROOT, "data", "wikidata_usa_93.db")
MANIFEST_PATH = os.path.join(ROOT, "data", "wikidata_usa_93_manifest.json")

# Properties needed by the 93 statements beyond the FEVER-extraction list:
# counts, seats, membership, offices, symbols, time zones, coordinates.
EXTRA_PROPERTIES = [
    "P1082",   # population
    "P1128",   # employees
    "P150",    # contains administrative territorial entity
    "P194",    # legislative body
    "P1342",   # number of seats
    "P463",    # member of
    "P6",      # head of government
    "P35",     # head of state
    "P85",     # anthem
    "P421",    # time zone
    "P625",    # coordinate location
    "P163",    # flag
]
PROPERTIES = list(dict.fromkeys(ext.PROPERTIES + EXTRA_PROPERTIES))

# Full titles resolve cleanly through Wikipedia pageprops. Generic forms
# ("Congress", "Senate", "House", "US") are excluded below and covered here.
CURATED = [
    "United States",
    "United States Congress",
    "United States Senate",
    "United States House of Representatives",
    "Supreme Court of the United States",
    "President of the United States",
    "Vice President of the United States",
    "United States Constitution",
    "United States Bill of Rights",
    "United States Declaration of Independence",
    "Federal Reserve System",
    "United States Department of Defense",
    "United States Department of the Treasury",
    "United States Armed Forces",
    "United States Electoral College",
    "United States federal government",
    "Democratic Party (United States)",
    "Republican Party (United States)",
    "Washington, D.C.",
    "New York City",
    "Chicago",
    "Alaska",
    "California",
    "George Washington",
    "Yellowstone National Park",
    "Baseball",
    "United Nations",
    "United Nations Security Council",
    "Apollo 11",
    "Moon",
    "English language",
    "French language",
    "Euro",
    "Pound sterling",
    "Japanese yen",
    "United States dollar",
    "Bald eagle",
    "Rose",
    "American bison",
    "Penguin",
    "Kangaroo",
    "Ostrich",
    "Lion",
    "Cactus",
    "Cricket",
    "Oak",
    "Diamond",
    "Square dance",
    "Flag of the United States",
    "The Star-Spangled Banner",
    "God Save the King",
    "North America",
    "South America",
    "Africa",
    "Oceania",
    "Arctic Circle",
    "Northern Hemisphere",
    "Southern Hemisphere",
    "Europe",
    "Asia",
]

# Names that resolve to the wrong sense or are extraction fragments.
# Additional entities named in the 93 statements but not covered above.
ENTITY_NAMES = CURATED + [
    "United Nations General Assembly",
    "Parliament of the United Kingdom",
    "Christopher Columbus",
]


def candidate_names(statements: list) -> set:
    """Curated entity list derived from the 93 statements.

    The list is intentionally explicit rather than NER-derived: spaCy NER
    on the statements yields fragments ("Rights", "D.C.", "the United
    States") that resolve to the wrong sense and bloat the DB. Every
    entity that can carry a fact for these statements is listed above and
    recorded in the manifest, so the slice is auditable.
    """
    return set(ENTITY_NAMES)


def _claim_year(claim) -> int | None:
    """Year of a time-valued claim's mainsnak, or None."""
    dv = claim.get("mainsnak", {}).get("datavalue", {})
    if dv.get("type") != "time":
        return None
    t = dv.get("value", {}).get("time", "")
    m = t.lstrip("+").split("-")
    try:
        return int(m[0])
    except (ValueError, IndexError):
        return None


# Properties where multiple values describe a time series or a current
# state. Wikidata marks the current value `preferred`; keeping the rest
# (historical capitals, historical populations, every past president)
# would make present-tense claims confirm against the wrong era.
PREFERRED_ONLY = {"P36", "P30", "P1082", "P6", "P35", "P31"}

# Current-relation properties whose historical rows carry an end time (P582).
# New York City's "capital of the United States" (1785-1790) and the USA's
# ended memberships (G8, NAFTA, ...) must not ground present-tense claims.
ENDED_FILTER = {"P36", "P1376", "P30", "P1082", "P6", "P35", "P31", "P463"}


def _has_past_end(claim, current_year: int) -> bool:
    for q in claim.get("qualifiers", {}).get("P582", []):
        t = q.get("datavalue", {}).get("value", {}).get("time", "")
        try:
            year = int(t.lstrip("+").split("-")[0])
        except (ValueError, IndexError):
            continue
        if year < current_year:
            return True
    return False


def select_claims(prop: str, claims: list) -> list:
    """Drop deprecated, ended, and non-preferred current-state claims."""
    live = [c for c in claims if c.get("rank") != "deprecated"]
    current_year = int(time.strftime("%Y"))
    if prop in ENDED_FILTER:
        live = [c for c in live if not _has_past_end(c, current_year)]
    if prop in PREFERRED_ONLY:
        preferred = [c for c in live if c.get("rank") == "preferred"]
        if preferred:
            live = preferred
    if prop == "P571":
        # Guard against future-dated inception values (Q11698 currently has
        # one: +2026-09-17). A future inception cannot ground a claim.
        live = [c for c in live if (_claim_year(c) or 0) <= current_year]
    return live


def upsert_entities(conn: sqlite3.Connection, entities_data: dict,
                    label_map: dict) -> dict:
    """Refresh labels/aliases and merge fetched claims into the DB."""
    added_entities = 0
    added_claims = 0
    added_aliases = 0
    refreshed = []

    for qid, data in entities_data.items():
        exists = conn.execute(
            "SELECT 1 FROM entities WHERE qid = ?", (qid,)
        ).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO entities (qid, label, label_lower, description) "
            "VALUES (?, ?, ?, COALESCE((SELECT description FROM entities WHERE qid=?), ?))",
            (qid, data["label"], data["label"].lower(), qid, "USA-93 Wikidata fetch"),
        )
        if not exists:
            added_entities += 1

        for alias in data["aliases"]:
            alias_lower = alias.lower().strip()
            if not alias_lower:
                continue
            row = conn.execute(
                "SELECT 1 FROM aliases WHERE qid=? AND alias_lower=?", (qid, alias_lower)
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO aliases (qid, alias_lower) VALUES (?, ?)",
                    (qid, alias_lower),
                )
                added_aliases += 1

        # Merge rather than replace: the seed carries curated facts that
        # Wikidata lacks (for example Q30 P37 = English). Identical rows are
        # skipped; selected historical rows never enter the DB.
        existing = set()
        for row in conn.execute(
            "SELECT property, value, value_qid FROM claims WHERE qid=?", (qid,)
        ):
            existing.add((row[0], row[1], row[2] or ""))
        for prop, claim_list in data["claims"].items():
            for claim in select_claims(prop, claim_list):
                snak = claim.get("mainsnak", {})
                formatted = ext.format_claim_value(snak, label_map)
                if not formatted:
                    continue
                value_str, value_qid = formatted
                key = (prop, value_str, value_qid or "")
                if key in existing:
                    continue
                conn.execute(
                    "INSERT INTO claims (qid, property, value, value_qid) "
                    "VALUES (?, ?, ?, ?)",
                    (qid, prop, value_str, value_qid),
                )
                existing.add(key)
                added_claims += 1
        refreshed.append(qid)

    # Label-only rows for referenced entities. INSERT OR IGNORE keeps
    # pre-existing labels and never deletes anything.
    for qid, label in label_map.items():
        if qid in entities_data:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO entities (qid, label, label_lower, description) "
            "VALUES (?, ?, ?, ?)",
            (qid, label, label.lower(), "referenced entity (USA-93 fetch)"),
        )
    return {
        "entities_added": added_entities,
        "claims_added": added_claims,
        "aliases_added": added_aliases,
        "refreshed_entities": len(refreshed),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--seed", default=SEED_DB)
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--manifest", default=MANIFEST_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    d = json.load(open(args.dataset))
    statements = [item["statement"] for item in d["items"]]
    print(f"Dataset: {args.dataset} ({len(statements)} statements)")

    names = candidate_names(statements)
    print(f"Candidate entity names: {len(names)}")

    if args.dry_run:
        for n in sorted(names):
            print("  ", n)
        return

    if not os.path.exists(args.target):
        shutil.copyfile(args.seed, args.target)
        print(f"Copied seed DB -> {args.target}")
    else:
        print(f"Using existing target DB: {args.target}")

    print(f"\nResolving {len(names)} names -> Wikidata QIDs ...")
    qid_map, unresolved = ext.resolve_names(names)
    print(f"  resolved {len(qid_map)}; unresolved {len(unresolved)}")

    print(f"\nFetching entity data for {len(qid_map)} QIDs ...")
    entities_data = ext.fetch_entities(set(qid_map.values()), properties=PROPERTIES)
    print(f"  fetched {len(entities_data)} entities")

    referenced = set()
    for data in entities_data.values():
        for prop_claims in data["claims"].values():
            for claim in prop_claims:
                dv = claim.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") in ("wikibase-item", "wikibase-entityid"):
                    v = dv.get("value", {})
                    rqid = v.get("id") or f"Q{v.get('numeric-id')}"
                    if rqid and rqid not in entities_data:
                        referenced.add(rqid)
    print(f"  resolving labels for {len(referenced)} referenced QIDs ...")
    ref_labels = ext.fetch_labels(referenced) if referenced else {}

    label_map = {qid: data["label"] for qid, data in entities_data.items()}
    label_map.update(ref_labels)

    print(f"\nWriting {args.target} ...")
    conn = sqlite3.connect(args.target)
    stats = upsert_entities(conn, entities_data, label_map)
    conn.commit()
    total_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    total_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    total_aliases = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    conn.close()

    by_name = {}
    for name, qid in qid_map.items():
        by_name[name] = {"qid": qid, "label": label_map.get(qid, qid)}
    manifest = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": os.path.relpath(args.dataset, ROOT),
        "seed_db": os.path.relpath(args.seed, ROOT),
        "target_db": os.path.relpath(args.target, ROOT),
        "properties": PROPERTIES,
        "rank_filter": {
            "preferred_only": sorted(PREFERRED_ONLY),
            "drop_if_ended": sorted(ENDED_FILTER),
            "dropped": [
                "deprecated (all properties)",
                "claims with a past P582 end time for current-relation properties",
                "future-dated P571",
            ],
            "note": (
                "Time-series and current-state properties keep the preferred "
                "Wikidata value only; ended historical relations are dropped; "
                "other properties keep all non-deprecated values. The seed's "
                "curated claims are merged, never deleted."
            ),
        },
        "counts": {
            "statements": len(statements),
            "candidate_names": len(names),
            "resolved_names": len(qid_map),
            "unresolved_names": len(unresolved),
            "entities_fetched": len(entities_data),
            "entities_added": stats["entities_added"],
            "entities_refreshed": stats["refreshed_entities"],
            "claims_added": stats["claims_added"],
            "aliases_added": stats["aliases_added"],
            "total_entities": total_entities,
            "total_claims": total_claims,
            "total_aliases": total_aliases,
        },
        "resolved": by_name,
        "unresolved": sorted(unresolved),
        "api": {
            "wikipedia": ext.WIKIPEDIA_API,
            "wikidata": ext.WIKIDATA_API,
            "user_agent": ext.USER_AGENT,
            "cache_dir": ext.CACHE_DIR,
        },
    }
    with open(args.manifest, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print("\n" + "=" * 60)
    print(f"  Target DB:        {args.target}")
    print(f"  Manifest:         {args.manifest}")
    print(f"  Entities fetched: {len(entities_data)}")
    print(f"  Entities added:   {stats['entities_added']}")
    print(f"  Entities refreshed: {stats['refreshed_entities']}")
    print(f"  Claims written:   {stats['claims_added']}")
    print(f"  Total entities:   {total_entities}")
    print(f"  Total claims:     {total_claims}")
    print(f"  Total aliases:    {total_aliases}")
    print("=" * 60)


if __name__ == "__main__":
    main()
