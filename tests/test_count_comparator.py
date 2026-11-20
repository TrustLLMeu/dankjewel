"""C0b: count-claim comparator (offline, exact-match, no territory in count).

Covers the six probe items plus territory filter, including possessive
chamber subjects ("The USA's Senate") and the seed-KB no-regression
(abstains when P150/P1342 absent). No network.
"""
import sqlite3
import pytest
from src.resources.wikidata_offline import OfflineWikidata, VerificationResult

from tests.test_five_way import _build_gate_fixture_db


def _count_fixture_db(tmp_path):
    """Minimal DB with USA P150 + chamber P1342 matching the usa_93 slice."""
    import pathlib
    path = pathlib.Path(tmp_path) / "count.db"
    _build_gate_fixture_db(
        path,
        entities=[
            ("Q30", "United States"),
            ("Q66096", "United States Senate"),
            ("Q11701", "United States House of Representatives"),
            ("Q11268", "United States Congress"),
        ],
        claims=[
            # USA P150: 50 states = 2 real states + Q816 Arizona stand-in + 47 synthetic state QIDs (Q200..Q246)
            # Territories that must be filtered are interleaved.
            # For brevity, tests inject them directly; see test_usa_states_territory_filter.
        ],
        aliases=[("Q30", "usa"), ("Q30", "united states"), ("Q66096", "senate of the united states"),
                 ("Q11701", "house of representatives of the united states")],
    )
    return path


class TestUSAStatesCount:
    """USA P150 filtered count: states vs territories."""

    def test_50_states_confirms(self, tmp_path):
        from src.resources.wikidata_offline import _TERRITORY_SUBSTRINGS
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        # Inject 49 real state values + Q816 + one territory
        states = [f"State{i}" for i in range(1, 50)] + ["Q816"]
        for v in states + ["Puerto Rico", "District of Columbia", "American Samoa"]:
            conn.execute("INSERT INTO claims (qid, property, value) VALUES ('Q30','P150',?)", (v,))
        conn.execute("INSERT INTO claims (qid, property, value, value_qid) VALUES ('Q66096','P1342','100',NULL)")
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        assert wd._count_claim_kb_count("The USA", "52 states") == 50
        d = wd.verify_triple("The USA", "have", "52 states")
        assert d.result == VerificationResult.DENIED
        assert d.property_id == "P150"
        assert d.wikidata_value == "50"
        d = wd.verify_triple("The United States", "have", "50 states")
        assert d.result == VerificationResult.CONFIRMED

    def test_usa_200_states_denies(self, tmp_path):
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        for v in [f"State{i}" for i in range(1, 50)] + ["Q816"] + ["Puerto Rico"]:
            conn.execute("INSERT INTO claims (qid, property, value) VALUES ('Q30','P150',?)", (v,))
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        d = wd.verify_triple("The USA", "have", "200 states")
        assert d.result == VerificationResult.DENIED
        assert d.wikidata_value == "50"

    def test_territory_filter_excludes_district_and_islands(self, tmp_path):
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        for v in ["Alabama", "Alaska", "District of Columbia", "Puerto Rico", "Guam", "American Samoa", "Territory of Alaska"]:
            conn.execute("INSERT INTO claims (qid, property, value) VALUES ('Q30','P150',?)", (v,))
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        # 2 states + 5 territories -> count 2
        assert wd._count_claim_kb_count("The USA", "3 states") == 2
        assert wd.verify_triple("The USA", "have", "2 states").result == VerificationResult.CONFIRMED
        assert wd.verify_triple("The USA", "have", "7 states").result == VerificationResult.DENIED

    def test_non_count_object_does_not_trigger(self, tmp_path):
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        for v in ["Alabama", "Alaska"]:
            conn.execute("INSERT INTO claims (qid, property, value) VALUES ('Q30','P150',?)", (v,))
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        # Object without count head noun bypasses count path
        assert wd._is_count_object("no coastline") is False
        assert wd._is_count_object("a country") is False
        assert wd._is_count_object("100 members") is True
        assert wd._is_count_object("52 states") is True


class TestChamberSeats:
    def test_senate_100_confirms_500_denies(self, tmp_path):
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        conn.execute("INSERT INTO claims (qid, property, value, value_qid) VALUES ('Q66096','P1342','100',NULL)")
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        assert wd.verify_triple("The Senate", "have", "100 members two per state").result == VerificationResult.CONFIRMED
        assert wd.verify_triple("The USA 's Senate", "have", "500 members").result == VerificationResult.DENIED

    def test_house_435_confirms_10_denies(self, tmp_path):
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        conn.execute("INSERT INTO claims (qid, property, value, value_qid) VALUES ('Q11701','P1342','435',NULL)")
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        assert wd.verify_triple("The House of Representatives", "have", "435 voting members").result == VerificationResult.CONFIRMED
        assert wd.verify_triple("The USA 's House of Representatives", "have", "10 members").result == VerificationResult.DENIED

    def test_count_triggers_before_possessive_decomposition(self, tmp_path):
        """'The USA's Senate' must route to chamber seats, not USA possessive."""
        path = _count_fixture_db(tmp_path)
        conn = sqlite3.connect(str(path))
        conn.execute("INSERT INTO claims (qid, property, value, value_qid) VALUES ('Q66096','P1342','100',NULL)")
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        # Possessive decomposition of this subject would be ("USA","P1342") -> Q30 no P1342 -> None
        # Count path must win and resolve to Q66096
        d = wd.verify_triple("The USA 's Senate", "have", "500 members")
        assert d.result == VerificationResult.DENIED
        assert d.subject_qid == "Q66096"


class TestSeedNoRegression:
    """Seed KB has no P150/P1342: count claims must abstain, not deny."""

    def test_seed_usa_states_abstains(self):
        wd = OfflineWikidata(db_path="data/wikidata_seed.db")
        d = wd.verify_triple("The United States", "have", "50 states")
        assert d.result == VerificationResult.UNKNOWN
        assert d.property_id == "P39" or d.property_id is None  # falls to have->P39, no P150 claim

    def test_seed_senate_abstains(self):
        wd = OfflineWikidata(db_path="data/wikidata_seed.db")
        d = wd.verify_triple("The Senate", "have", "100 members two per state")
        assert d.result == VerificationResult.UNKNOWN


class TestExitCriteria:
    """C0b exit criteria on the 93-set (extended KB). Offline, no egress."""

    def test_extended_kb_meets_c0b_exit_criteria(self):
        """6 count items decide correctly; overall gates hold."""
        wd = OfflineWikidata(db_path="data/wikidata_usa_93.db")
        cases = [
            ("The United States", "have", "50 states", VerificationResult.CONFIRMED),
            ("The Senate", "have", "100 members two per state", VerificationResult.CONFIRMED),
            ("The House of Representatives", "have", "435 voting members", VerificationResult.CONFIRMED),
            ("The USA", "have", "52 states", VerificationResult.DENIED),
            ("The USA 's Senate", "have", "500 members", VerificationResult.DENIED),
            ("The USA", "have", "200 states", VerificationResult.DENIED),
            ("The USA 's House of Representatives", "have", "10 members", VerificationResult.DENIED),
        ]
        for subj, pred, obj, expected in cases:
            d = wd.verify_triple(subj, pred, obj)
            assert d.result == expected, f"{subj!r} {obj!r}: expected {expected}, got {d.result} ({d.property_id}={d.wikidata_value})"
