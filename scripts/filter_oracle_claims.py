#!/usr/bin/env python3
"""Filter a FEVER oracle sample to only claims whose evidence entities exist in the DB.

Use after build_fever_wikidata.py if the build was cut short by rate limiting
(HTTP 429) and only a subset of entities were downloaded. Produces a filtered
sample file that eval_fever2.py can consume directly — no changes to the eval
script needed.

Usage:
    python scripts/filter_oracle_claims.py
    python scripts/filter_oracle_claims.py data/wikidata_fever.db data/fever2_oracle_sample.jsonl data/fever2_oracle_filtered.jsonl
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DB_PATH = "data/wikidata_fever.db"
IN_PATH = "data/fever2_oracle_sample.jsonl"
OUT_PATH = "data/fever2_oracle_filtered.jsonl"


def clean_title(t):
    """Decode FEVER's Wikipedia title encoding (must match build_fever_wikidata.py)."""
    t = t.replace("-LRB-", "(").replace("-RRB-", ")")
    t = t.replace("-LSB-", "[").replace("-RSB-", "]")
    t = t.replace("-COLON-", ":")
    t = t.replace("_", " ")
    return t.strip().lower()


def main():
    db, inp, outp = DB_PATH, IN_PATH, OUT_PATH
    args = sys.argv[1:]
    if len(args) >= 1:
        db = args[0]
    if len(args) >= 2:
        inp = args[1]
    if len(args) >= 3:
        outp = args[2]

    # Load all entity labels + aliases from the DB (lowercased)
    conn = sqlite3.connect(db)
    names = set()
    for row in conn.execute("SELECT label_lower FROM entities"):
        names.add(row[0])
    for row in conn.execute("SELECT alias_lower FROM aliases"):
        names.add(row[0])
    n_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    conn.close()

    # Load the claim sample
    claims = []
    with open(inp) as f:
        for line in f:
            line = line.strip()
            if line:
                claims.append(json.loads(line))

    # Keep a claim iff at least one of its evidence entity titles is in the DB
    kept = []
    for c in claims:
        hit = False
        for evidence_set in c.get("evidence", []) or []:
            if not isinstance(evidence_set, list):
                continue
            for ev in evidence_set:
                if isinstance(ev, list) and len(ev) >= 3 and ev[2]:
                    if clean_title(str(ev[2])) in names:
                        hit = True
                        break
            if hit:
                break
        if hit:
            kept.append(c)

    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w") as f:
        for c in kept:
            f.write(json.dumps(c) + "\n")

    cnt = Counter(c["label"] for c in kept)
    print(f"DB entities:            {n_entities}")
    print(f"DB labels+aliases:      {len(names)} lookup keys")
    print(f"Input claims:           {len(claims)}")
    print(f"Kept claims (in-DB):    {len(kept)} "
          f"({len(kept)/len(claims)*100:.1f}% of sample)")
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        print(f"  {label:<18} {cnt.get(label, 0)}")
    print(f"\nWrote: {outp}")
    print(f"\nNow run eval with:")
    print(f"  python scripts/eval_fever2.py \\")
    print(f"    --db-path {db} \\")
    print(f"    --sample-path {outp} \\")
    print(f"    --output-suffix oracle")


if __name__ == "__main__":
    main()
