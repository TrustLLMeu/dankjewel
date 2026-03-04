"""Build an offline Wikidata seed database (SQLite) for fact-checking.

Downloads a subset of Wikidata and writes ~200k entities with English labels
into a local SQLite database. This seed covers countries, cities, geography,
notable people, organizations, and dated events.

Usage:
    python scripts/build_wikidata_db.py [--output data/wikidata_seed.db]

Since downloading the full Wikidata dump is impractical for development,
this script bootstraps a usable seed from the Wikidata SPARQL endpoint
using batched queries, OR populates from a curated hardcoded set for
immediate offline use.

Phase 1: Hardcoded seed with ~500 well-known facts for testing/demo.
Phase 2 (future): SPARQL-based bulk download for 200k entities.
"""

import sqlite3
import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_schema(conn: sqlite3.Connection):
    """Create the database schema."""
    conn.executescript("""
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
    """)


# ── Property ID reference ──────────────────────────────────────────────────
# P17  = country
# P36  = capital
# P131 = located in administrative territorial entity
# P625 = coordinate location
# P610 = highest point
# P1082 = population
# P571 = inception / founded
# P569 = date of birth
# P570 = date of death
# P27  = country of citizenship
# P106 = occupation
# P580 = start time
# P582 = end time
# P585 = point in time
# P1376 = capital of
# P30  = continent
# P47  = shares border with
# P37  = official language
# P38  = currency
# P2044 = elevation above sea level
# P206 = located on body of water
# P1001 = applies to jurisdiction

SEED_DATA = {
    # ── Countries and capitals ──────────────────────────────────────────
    "Q142": {
        "label": "France",
        "aliases": ["french republic", "république française"],
        "description": "country in Western Europe",
        "claims": [
            ("P36", "Paris", "Q90"),
            ("P30", "Europe", "Q46"),
            ("P37", "French", "Q150"),
            ("P38", "Euro", "Q4916"),
        ]
    },
    "Q90": {
        "label": "Paris",
        "aliases": ["city of paris", "paris, france"],
        "description": "capital of France",
        "claims": [
            ("P17", "France", "Q142"),
            ("P1376", "France", "Q142"),
            ("P131", "Île-de-France", "Q13917"),
        ]
    },
    "Q20": {
        "label": "Norway",
        "aliases": ["kingdom of norway", "norge", "noreg"],
        "description": "country in Northern Europe",
        "claims": [
            ("P36", "Oslo", "Q585"),
            ("P30", "Europe", "Q46"),
            ("P37", "Norwegian", "Q9043"),
            ("P38", "Norwegian krone", "Q132588"),
        ]
    },
    "Q585": {
        "label": "Oslo",
        "aliases": ["christiania", "oslo, norway"],
        "description": "capital of Norway",
        "claims": [
            ("P17", "Norway", "Q20"),
            ("P1376", "Norway", "Q20"),
            ("P131", "Oslo", "Q585"),
        ]
    },
    "Q25437": {
        "label": "Tromsø",
        "aliases": ["tromso", "tromsø, norway", "troms", "tromsoe"],
        "description": "city in Troms og Finnmark, Norway",
        "claims": [
            ("P17", "Norway", "Q20"),
            ("P131", "Troms og Finnmark", "Q50624"),
        ]
    },
    "Q183": {
        "label": "Germany",
        "aliases": ["federal republic of germany", "deutschland", "brd"],
        "description": "country in Central Europe",
        "claims": [
            ("P36", "Berlin", "Q64"),
            ("P30", "Europe", "Q46"),
            ("P37", "German", "Q188"),
            ("P38", "Euro", "Q4916"),
        ]
    },
    "Q64": {
        "label": "Berlin",
        "aliases": ["berlin, germany"],
        "description": "capital of Germany",
        "claims": [
            ("P17", "Germany", "Q183"),
            ("P1376", "Germany", "Q183"),
        ]
    },
    "Q145": {
        "label": "United Kingdom",
        "aliases": ["uk", "britain", "great britain", "united kingdom of great britain and northern ireland"],
        "description": "country in Europe",
        "claims": [
            ("P36", "London", "Q84"),
            ("P30", "Europe", "Q46"),
            ("P37", "English", "Q1860"),
            ("P38", "Pound sterling", "Q25224"),
        ]
    },
    "Q84": {
        "label": "London",
        "aliases": ["london, england", "city of london"],
        "description": "capital of the United Kingdom",
        "claims": [
            ("P17", "United Kingdom", "Q145"),
            ("P1376", "United Kingdom", "Q145"),
            ("P131", "England", "Q21"),
        ]
    },
    "Q30": {
        "label": "United States of America",
        "aliases": ["usa", "united states", "us", "america"],
        "description": "country in North America",
        "claims": [
            ("P36", "Washington, D.C.", "Q61"),
            ("P30", "North America", "Q49"),
            ("P37", "English", "Q1860"),
            ("P38", "United States dollar", "Q4917"),
        ]
    },
    "Q61": {
        "label": "Washington, D.C.",
        "aliases": ["washington dc", "washington d.c.", "dc"],
        "description": "capital of the United States",
        "claims": [
            ("P17", "United States of America", "Q30"),
            ("P1376", "United States of America", "Q30"),
        ]
    },
    "Q17": {
        "label": "Japan",
        "aliases": ["nippon", "nihon"],
        "description": "island country in East Asia",
        "claims": [
            ("P36", "Tokyo", "Q1490"),
            ("P30", "Asia", "Q48"),
            ("P37", "Japanese", "Q5287"),
            ("P38", "Japanese yen", "Q8146"),
        ]
    },
    "Q1490": {
        "label": "Tokyo",
        "aliases": ["tokyo, japan"],
        "description": "capital of Japan",
        "claims": [
            ("P17", "Japan", "Q17"),
            ("P1376", "Japan", "Q17"),
        ]
    },
    "Q38": {
        "label": "Italy",
        "aliases": ["italian republic", "italia"],
        "description": "country in Southern Europe",
        "claims": [
            ("P36", "Rome", "Q220"),
            ("P30", "Europe", "Q46"),
            ("P37", "Italian", "Q652"),
            ("P38", "Euro", "Q4916"),
        ]
    },
    "Q220": {
        "label": "Rome",
        "aliases": ["roma", "rome, italy"],
        "description": "capital of Italy",
        "claims": [
            ("P17", "Italy", "Q38"),
            ("P1376", "Italy", "Q38"),
        ]
    },
    "Q29": {
        "label": "Spain",
        "aliases": ["kingdom of spain", "españa"],
        "description": "country in Southern Europe",
        "claims": [
            ("P36", "Madrid", "Q2807"),
            ("P30", "Europe", "Q46"),
            ("P37", "Spanish", "Q1321"),
            ("P38", "Euro", "Q4916"),
        ]
    },
    "Q2807": {
        "label": "Madrid",
        "aliases": ["madrid, spain"],
        "description": "capital of Spain",
        "claims": [
            ("P17", "Spain", "Q29"),
            ("P1376", "Spain", "Q29"),
        ]
    },
    "Q159": {
        "label": "Russia",
        "aliases": ["russian federation"],
        "description": "country in Eastern Europe and North Asia",
        "claims": [
            ("P36", "Moscow", "Q649"),
            ("P30", "Europe", "Q46"),
            ("P37", "Russian", "Q7737"),
        ]
    },
    "Q649": {
        "label": "Moscow",
        "aliases": ["moscow, russia", "moskva"],
        "description": "capital of Russia",
        "claims": [
            ("P17", "Russia", "Q159"),
            ("P1376", "Russia", "Q159"),
        ]
    },
    "Q148": {
        "label": "China",
        "aliases": ["people's republic of china", "prc", "zhongguo"],
        "description": "country in East Asia",
        "claims": [
            ("P36", "Beijing", "Q956"),
            ("P30", "Asia", "Q48"),
            ("P37", "Mandarin Chinese", "Q9192"),
        ]
    },
    "Q956": {
        "label": "Beijing",
        "aliases": ["peking", "beijing, china"],
        "description": "capital of China",
        "claims": [
            ("P17", "China", "Q148"),
            ("P1376", "China", "Q148"),
        ]
    },
    "Q35": {
        "label": "Denmark",
        "aliases": ["kingdom of denmark", "danmark"],
        "description": "country in Northern Europe",
        "claims": [
            ("P36", "Copenhagen", "Q1748"),
            ("P30", "Europe", "Q46"),
            ("P37", "Danish", "Q9035"),
            ("P38", "Danish krone", "Q25417"),
        ]
    },
    "Q1748": {
        "label": "Copenhagen",
        "aliases": ["københavn", "copenhagen, denmark"],
        "description": "capital of Denmark",
        "claims": [
            ("P17", "Denmark", "Q35"),
            ("P1376", "Denmark", "Q35"),
        ]
    },
    "Q34": {
        "label": "Sweden",
        "aliases": ["kingdom of sweden", "sverige"],
        "description": "country in Northern Europe",
        "claims": [
            ("P36", "Stockholm", "Q1754"),
            ("P30", "Europe", "Q46"),
            ("P37", "Swedish", "Q9027"),
            ("P38", "Swedish krona", "Q122922"),
        ]
    },
    "Q1754": {
        "label": "Stockholm",
        "aliases": ["stockholm, sweden"],
        "description": "capital of Sweden",
        "claims": [
            ("P17", "Sweden", "Q34"),
            ("P1376", "Sweden", "Q34"),
        ]
    },
    "Q33": {
        "label": "Finland",
        "aliases": ["republic of finland", "suomi"],
        "description": "country in Northern Europe",
        "claims": [
            ("P36", "Helsinki", "Q1757"),
            ("P30", "Europe", "Q46"),
            ("P37", "Finnish", "Q1412"),
            ("P38", "Euro", "Q4916"),
        ]
    },
    "Q4628": {
        "label": "Faroe Islands",
        "aliases": ["faroe", "faroes", "føroyar"],
        "description": "autonomous territory of the Kingdom of Denmark",
        "claims": [
            ("P36", "Tórshavn", "Q25895"),
            ("P17", "Denmark", "Q35"),
            ("P30", "Europe", "Q46"),
            ("P37", "Faroese", "Q25258"),
        ]
    },
    "Q55": {
        "label": "Netherlands",
        "aliases": ["holland", "the netherlands", "kingdom of the netherlands"],
        "description": "country in Western Europe",
        "claims": [
            ("P36", "Amsterdam", "Q727"),
            ("P30", "Europe", "Q46"),
            ("P37", "Dutch", "Q7411"),
            ("P38", "Euro", "Q4916"),
        ]
    },

    # ── Geography / Mountains ───────────────────────────────────────────
    "Q513": {
        "label": "Mount Everest",
        "aliases": ["everest", "sagarmatha", "chomolungma", "mt everest", "mt. everest"],
        "description": "highest mountain on Earth",
        "claims": [
            ("P17", "Nepal", "Q837"),
            ("P2044", "8849 m", None),
            ("P610", "Mount Everest", "Q513"),  # highest point is itself
        ]
    },
    "Q837": {
        "label": "Nepal",
        "aliases": ["federal democratic republic of nepal"],
        "description": "country in South Asia",
        "claims": [
            ("P36", "Kathmandu", "Q3551"),
            ("P30", "Asia", "Q48"),
        ]
    },
    "Q235": {
        "label": "Monaco",
        "aliases": ["principality of monaco"],
        "description": "city-state and microstate on the French Riviera",
        "claims": [
            ("P30", "Europe", "Q46"),
        ]
    },
    "Q5813": {
        "label": "K2",
        "aliases": ["mount godwin-austen", "chhogori"],
        "description": "second-highest mountain on Earth",
        "claims": [
            ("P2044", "8611 m", None),
            ("P17", "Pakistan", "Q843"),
        ]
    },

    # ── Rivers / Bodies of water ────────────────────────────────────────
    "Q1653": {
        "label": "Amazon River",
        "aliases": ["amazon", "rio amazonas"],
        "description": "major river in South America",
        "claims": [
            ("P17", "Brazil", "Q155"),
            ("P30", "South America", "Q18"),
        ]
    },
    "Q584": {
        "label": "Nile",
        "aliases": ["nile river", "river nile"],
        "description": "major river in Africa",
        "claims": [
            ("P30", "Africa", "Q15"),
        ]
    },

    # ── People ──────────────────────────────────────────────────────────
    "Q5592": {
        "label": "Albert Einstein",
        "aliases": ["einstein"],
        "description": "German-born theoretical physicist (1879–1955)",
        "claims": [
            ("P569", "1879-03-14", None),
            ("P570", "1955-04-18", None),
            ("P27", "United States of America", "Q30"),
            ("P106", "physicist", None),
        ]
    },
    "Q937": {
        "label": "Albert Einstein",
        "aliases": ["einstein"],
        "description": "German-born theoretical physicist (1879–1955)",
        "claims": [
            ("P569", "1879-03-14", None),
            ("P570", "1955-04-18", None),
            ("P27", "United States of America", "Q30"),
            ("P106", "physicist", None),
        ]
    },
    "Q1299": {
        "label": "The Beatles",
        "aliases": ["beatles"],
        "description": "English rock band",
        "claims": [
            ("P17", "United Kingdom", "Q145"),
            ("P571", "1960", None),
        ]
    },
    "Q15869": {
        "label": "Queen",
        "aliases": ["queen band", "queen rock band"],
        "description": "British rock band",
        "claims": [
            ("P17", "United Kingdom", "Q145"),
            ("P571", "1970", None),
        ]
    },
    "Q2831": {
        "label": "Michael Jackson",
        "aliases": ["king of pop", "mj"],
        "description": "American singer, songwriter, and dancer (1958–2009)",
        "claims": [
            ("P569", "1958-08-29", None),
            ("P570", "2009-06-25", None),
            ("P27", "United States of America", "Q30"),
            ("P106", "singer", None),
        ]
    },
    "Q1339": {
        "label": "Johann Sebastian Bach",
        "aliases": ["bach", "j.s. bach", "js bach"],
        "description": "German composer (1685–1750)",
        "claims": [
            ("P569", "1685-03-31", None),
            ("P570", "1750-07-28", None),
            ("P27", "Germany", "Q183"),
            ("P106", "composer", None),
        ]
    },
    "Q7186": {
        "label": "Marie Curie",
        "aliases": ["maria sklodowska-curie", "madame curie"],
        "description": "Polish-French physicist and chemist (1867–1934)",
        "claims": [
            ("P569", "1867-11-07", None),
            ("P570", "1934-07-04", None),
            ("P27", "France", "Q142"),
            ("P106", "physicist", None),
        ]
    },
    "Q9696": {
        "label": "John F. Kennedy",
        "aliases": ["jfk", "kennedy", "john fitzgerald kennedy"],
        "description": "35th president of the United States (1917–1963)",
        "claims": [
            ("P569", "1917-05-29", None),
            ("P570", "1963-11-22", None),
            ("P27", "United States of America", "Q30"),
            ("P106", "politician", None),
        ]
    },
    "Q692": {
        "label": "William Shakespeare",
        "aliases": ["shakespeare", "the bard"],
        "description": "English playwright (1564–1616)",
        "claims": [
            ("P569", "1564-04-26", None),
            ("P570", "1616-04-23", None),
            ("P27", "United Kingdom", "Q145"),
            ("P106", "playwright", None),
        ]
    },

    # ── Continents ──────────────────────────────────────────────────────
    "Q46": {
        "label": "Europe",
        "aliases": ["european continent"],
        "description": "continent",
        "claims": []
    },
    "Q48": {
        "label": "Asia",
        "aliases": ["asian continent"],
        "description": "continent",
        "claims": []
    },
    "Q49": {
        "label": "North America",
        "aliases": [],
        "description": "continent",
        "claims": []
    },
    "Q18": {
        "label": "South America",
        "aliases": [],
        "description": "continent",
        "claims": []
    },
    "Q15": {
        "label": "Africa",
        "aliases": ["african continent"],
        "description": "continent",
        "claims": []
    },

    # ── Additional cities and geographic facts ──────────────────────────
    "Q1055": {
        "label": "Hamburg",
        "aliases": ["hamburg, germany"],
        "description": "city in Germany",
        "claims": [
            ("P17", "Germany", "Q183"),
            ("P131", "Germany", "Q183"),
        ]
    },
    "Q1726": {
        "label": "Munich",
        "aliases": ["münchen", "munich, germany"],
        "description": "capital of Bavaria, Germany",
        "claims": [
            ("P17", "Germany", "Q183"),
            ("P131", "Bavaria", "Q980"),
        ]
    },
    "Q1218": {
        "label": "Knebworth",
        "aliases": ["knebworth house", "knebworth park"],
        "description": "village in Hertfordshire, England",
        "claims": [
            ("P17", "United Kingdom", "Q145"),
            ("P131", "Hertfordshire", "Q23298"),
        ]
    },
    "Q34217": {
        "label": "Arctic Circle",
        "aliases": ["arctic circle"],
        "description": "one of the five major circles of latitude",
        "claims": []
    },

    # ── Organizations ───────────────────────────────────────────────────
    "Q2283": {
        "label": "Wikipedia",
        "aliases": ["wiki"],
        "description": "free online encyclopedia",
        "claims": [
            ("P571", "2001-01-15", None),
            ("P17", "United States of America", "Q30"),
        ]
    },
    "Q312": {
        "label": "Apple Inc.",
        "aliases": ["apple", "apple computer"],
        "description": "American multinational technology company",
        "claims": [
            ("P571", "1976-04-01", None),
            ("P17", "United States of America", "Q30"),
        ]
    },

    # ── Historic events with dates ──────────────────────────────────────
    "Q362": {
        "label": "World War II",
        "aliases": ["wwii", "ww2", "second world war"],
        "description": "global war (1939–1945)",
        "claims": [
            ("P580", "1939-09-01", None),
            ("P582", "1945-09-02", None),
        ]
    },
    "Q361": {
        "label": "World War I",
        "aliases": ["wwi", "ww1", "first world war", "great war"],
        "description": "global war (1914–1918)",
        "claims": [
            ("P580", "1914-07-28", None),
            ("P582", "1918-11-11", None),
        ]
    },
    "Q11812": {
        "label": "French Revolution",
        "aliases": [],
        "description": "revolution in France (1789–1799)",
        "claims": [
            ("P580", "1789-05-05", None),
            ("P582", "1799-11-09", None),
            ("P17", "France", "Q142"),
        ]
    },

    # ── More Nordic coverage ────────────────────────────────────────────
    "Q25895": {
        "label": "Tórshavn",
        "aliases": ["torshavn", "thorshavn"],
        "description": "capital of the Faroe Islands",
        "claims": [
            ("P17", "Denmark", "Q35"),
            ("P1376", "Faroe Islands", "Q4628"),
        ]
    },
    "Q1757": {
        "label": "Helsinki",
        "aliases": ["helsingfors", "helsinki, finland"],
        "description": "capital of Finland",
        "claims": [
            ("P17", "Finland", "Q33"),
            ("P1376", "Finland", "Q33"),
        ]
    },
    "Q36": {
        "label": "Poland",
        "aliases": ["republic of poland", "polska"],
        "description": "country in Central Europe",
        "claims": [
            ("P36", "Warsaw", "Q270"),
            ("P30", "Europe", "Q46"),
        ]
    },
    "Q270": {
        "label": "Warsaw",
        "aliases": ["warszawa", "warsaw, poland"],
        "description": "capital of Poland",
        "claims": [
            ("P17", "Poland", "Q36"),
            ("P1376", "Poland", "Q36"),
        ]
    },

    # ── Oceans ──────────────────────────────────────────────────────────
    "Q97": {
        "label": "Atlantic Ocean",
        "aliases": ["atlantic"],
        "description": "ocean between the Americas and Africa/Europe",
        "claims": []
    },
    "Q98": {
        "label": "Pacific Ocean",
        "aliases": ["pacific"],
        "description": "largest and deepest ocean on Earth",
        "claims": []
    },

    # ── Planets ─────────────────────────────────────────────────────────
    "Q2": {
        "label": "Earth",
        "aliases": ["the earth", "world", "terra"],
        "description": "third planet from the Sun",
        "claims": []
    },
    "Q111": {
        "label": "Mars",
        "aliases": ["the red planet"],
        "description": "fourth planet from the Sun",
        "claims": []
    },

    # ── Additional countries ────────────────────────────────────────────
    "Q155": {
        "label": "Brazil",
        "aliases": ["federative republic of brazil", "brasil"],
        "description": "country in South America",
        "claims": [
            ("P36", "Brasília", "Q2844"),
            ("P30", "South America", "Q18"),
            ("P37", "Portuguese", "Q5146"),
        ]
    },
    "Q668": {
        "label": "India",
        "aliases": ["republic of india", "bharat"],
        "description": "country in South Asia",
        "claims": [
            ("P36", "New Delhi", "Q987"),
            ("P30", "Asia", "Q48"),
            ("P37", "Hindi", "Q1568"),
        ]
    },
    "Q408": {
        "label": "Australia",
        "aliases": ["commonwealth of australia"],
        "description": "country in Oceania",
        "claims": [
            ("P36", "Canberra", "Q3114"),
            ("P37", "English", "Q1860"),
        ]
    },
    "Q16": {
        "label": "Canada",
        "aliases": [],
        "description": "country in North America",
        "claims": [
            ("P36", "Ottawa", "Q1930"),
            ("P30", "North America", "Q49"),
            ("P37", "English", "Q1860"),
        ]
    },
    "Q96": {
        "label": "Mexico",
        "aliases": ["united mexican states"],
        "description": "country in North America",
        "claims": [
            ("P36", "Mexico City", "Q1489"),
            ("P30", "North America", "Q49"),
            ("P37", "Spanish", "Q1321"),
        ]
    },
    "Q414": {
        "label": "Argentina",
        "aliases": ["argentine republic"],
        "description": "country in South America",
        "claims": [
            ("P36", "Buenos Aires", "Q1486"),
            ("P30", "South America", "Q18"),
            ("P37", "Spanish", "Q1321"),
        ]
    },
    "Q79": {
        "label": "Egypt",
        "aliases": ["arab republic of egypt"],
        "description": "country in North Africa",
        "claims": [
            ("P36", "Cairo", "Q85"),
            ("P30", "Africa", "Q15"),
            ("P37", "Arabic", "Q13955"),
        ]
    },
    "Q258": {
        "label": "South Africa",
        "aliases": ["republic of south africa", "rsa"],
        "description": "country in Southern Africa",
        "claims": [
            ("P36", "Pretoria", "Q3926"),
            ("P30", "Africa", "Q15"),
        ]
    },
    "Q213": {
        "label": "Czech Republic",
        "aliases": ["czechia", "česko"],
        "description": "country in Central Europe",
        "claims": [
            ("P36", "Prague", "Q1085"),
            ("P30", "Europe", "Q46"),
        ]
    },
    "Q1085": {
        "label": "Prague",
        "aliases": ["praha", "prague, czech republic"],
        "description": "capital of the Czech Republic",
        "claims": [
            ("P17", "Czech Republic", "Q213"),
            ("P1376", "Czech Republic", "Q213"),
        ]
    },
    "Q28": {
        "label": "Hungary",
        "aliases": ["magyarország"],
        "description": "country in Central Europe",
        "claims": [
            ("P36", "Budapest", "Q1781"),
            ("P30", "Europe", "Q46"),
        ]
    },
    "Q1781": {
        "label": "Budapest",
        "aliases": ["budapest, hungary"],
        "description": "capital of Hungary",
        "claims": [
            ("P17", "Hungary", "Q28"),
            ("P1376", "Hungary", "Q28"),
        ]
    },
    "Q40": {
        "label": "Austria",
        "aliases": ["republic of austria", "österreich"],
        "description": "country in Central Europe",
        "claims": [
            ("P36", "Vienna", "Q1741"),
            ("P30", "Europe", "Q46"),
            ("P37", "German", "Q188"),
            ("P38", "Euro", "Q4916"),
        ]
    },
    "Q1741": {
        "label": "Vienna",
        "aliases": ["wien", "vienna, austria"],
        "description": "capital of Austria",
        "claims": [
            ("P17", "Austria", "Q40"),
            ("P1376", "Austria", "Q40"),
        ]
    },
    "Q39": {
        "label": "Switzerland",
        "aliases": ["swiss confederation", "schweiz", "suisse", "svizzera"],
        "description": "country in Central Europe",
        "claims": [
            ("P36", "Bern", "Q70"),
            ("P30", "Europe", "Q46"),
        ]
    },
    "Q41": {
        "label": "Greece",
        "aliases": ["hellenic republic", "hellas"],
        "description": "country in Southern Europe",
        "claims": [
            ("P36", "Athens", "Q1524"),
            ("P30", "Europe", "Q46"),
        ]
    },
    "Q1524": {
        "label": "Athens",
        "aliases": ["athina", "athens, greece"],
        "description": "capital of Greece",
        "claims": [
            ("P17", "Greece", "Q41"),
            ("P1376", "Greece", "Q41"),
        ]
    },
    "Q423": {
        "label": "North Korea",
        "aliases": ["dprk", "democratic people's republic of korea"],
        "description": "country in East Asia",
        "claims": [
            ("P36", "Pyongyang", "Q18808"),
            ("P30", "Asia", "Q48"),
        ]
    },
    "Q884": {
        "label": "South Korea",
        "aliases": ["republic of korea", "korea"],
        "description": "country in East Asia",
        "claims": [
            ("P36", "Seoul", "Q8684"),
            ("P30", "Asia", "Q48"),
        ]
    },
    "Q843": {
        "label": "Pakistan",
        "aliases": ["islamic republic of pakistan"],
        "description": "country in South Asia",
        "claims": [
            ("P36", "Islamabad", "Q11739"),
            ("P30", "Asia", "Q48"),
        ]
    },

    # ── Stockholm archipelago (needed for consistency test) ─────────────
    "Q541586": {
        "label": "Stockholm archipelago",
        "aliases": ["stockholms skärgård"],
        "description": "archipelago on the coast of Sweden",
        "claims": [
            ("P17", "Sweden", "Q34"),
            ("P131", "Stockholm County", "Q104231"),
        ]
    },
}


def populate_seed(conn: sqlite3.Connection):
    """Populate database with hardcoded seed data."""
    for qid, data in SEED_DATA.items():
        label = data["label"]
        label_lower = label.lower()
        description = data.get("description", "")

        conn.execute(
            "INSERT OR REPLACE INTO entities (qid, label, label_lower, description) VALUES (?, ?, ?, ?)",
            (qid, label, label_lower, description)
        )

        for alias in data.get("aliases", []):
            conn.execute(
                "INSERT INTO aliases (qid, alias_lower) VALUES (?, ?)",
                (qid, alias.lower())
            )

        for prop, value, value_qid in data.get("claims", []):
            conn.execute(
                "INSERT INTO claims (qid, property, value, value_qid) VALUES (?, ?, ?, ?)",
                (qid, prop, value, value_qid)
            )

    conn.commit()


def build_database(output_path: str):
    """Build the seed database."""
    # Remove existing DB
    if os.path.exists(output_path):
        os.remove(output_path)

    conn = sqlite3.connect(output_path)
    create_schema(conn)
    populate_seed(conn)

    # Stats
    entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    alias_count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    claim_count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    conn.close()

    print(f"✅ Wikidata seed database built: {output_path}")
    print(f"   Entities: {entity_count}")
    print(f"   Aliases:  {alias_count}")
    print(f"   Claims:   {claim_count}")
    print(f"   Size:     {os.path.getsize(output_path) / 1024:.1f} KB")
    print()
    print("NOTE: This is a Phase 1 seed with hardcoded facts for testing.")
    print("      Phase 2 will use SPARQL queries to populate ~200k entities.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build offline Wikidata seed database')
    parser.add_argument('--output', default='data/wikidata_seed.db',
                        help='Output path for SQLite database')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    build_database(args.output)

