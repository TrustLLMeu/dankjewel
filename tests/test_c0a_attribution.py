"""C0a attribution + router regression tests (harness-level).

Covers: decision_layer per claim/item, by_layer aggregates, false_confirms,
and per-bug-class pins for substring/possessive/superlative/location.
No network, CPU-only.
"""
import pytest
import scripts.attribution as attribution


# ── Attribution unit tests ───────────────────────────────────────────────

class TestAttributionForClaim:
    def test_confirmed_is_kb_exact(self):
        layer, reason = attribution.attribution_for_claim({"effective_result": "confirmed", "reason": None})
        assert layer == "kb_exact" and reason is None

    def test_denied_is_kb_exact(self):
        layer, reason = attribution.attribution_for_claim({"effective_result": "denied"})
        assert layer == "kb_exact"

    def test_conflated_is_kb_exact(self):
        layer, _ = attribution.attribution_for_claim({"effective_result": "conflated"})
        assert layer == "kb_exact"

    def test_unknown_is_abstain(self):
        layer, reason = attribution.attribution_for_claim({"effective_result": "unknown", "reason": "entity_not_in_kb"})
        assert layer == "abstain" and reason == "entity_not_in_kb"

    def test_verifier_off_is_abstain(self):
        layer, reason = attribution.attribution_for_claim({"effective_result": "unknown", "reason": "verifier_off"})
        assert layer == "abstain" and reason == "verifier_off"


class TestAttributionForItem:
    def test_zero_claims_abstain(self):
        layer, counts, fc = attribution.attribution_for_item([])
        assert layer == "abstain"
        assert counts == {"kb_exact": 0, "web": 0, "verifier": 0, "abstain": 0}

    def test_single_kb_exact(self):
        layer, counts, _ = attribution.attribution_for_item([{"effective_result": "denied"}])
        assert layer == "kb_exact" and counts["kb_exact"] == 1

    def test_single_abstain(self):
        layer, counts, _ = attribution.attribution_for_item([{"effective_result": "unknown", "reason": "verifier_off"}])
        assert layer == "abstain" and counts["abstain"] == 1


class TestByLayerMetrics:
    def test_empty_layer_accuracy_none(self):
        items = [
            {"ground_truth": "false", "off": {"prediction": "abstain", "decision_layer": "abstain", "layer_counts": {"kb_exact": 0, "web": 0, "verifier": 0, "abstain": 1}}},
        ]
        m = attribution.attribution_metrics(items, condition="off")
        assert m["by_layer"]["kb_exact"]["decided"] == 0
        assert m["by_layer"]["kb_exact"]["accuracy"] is None
        assert m["false_confirms"] == 0


# ── Router: substring (word-boundary) ───────────────────────────────────

class TestSubstringWordBoundary:
    """Africa inside African Development Bank — the classic false confirm."""
    def test_africa_not_substring_of_african_bank(self, tmp_path):
        import sqlite3
        from src.resources.wikidata_offline import OfflineWikidata, VerificationResult
        from tests.test_five_way import _build_gate_fixture_db
        path = tmp_path / "substr.db"
        _build_gate_fixture_db(path,
            entities=[("Q30", "United States"), ("Q15", "Africa"), ("Q340195", "African Development Bank")],
            claims=[("Q30", "P463", "African Development Bank", "Q340195"), ("Q30", "P30", "North America", "Q49")],
            aliases=[("Q30", "the usa")])
        conn = sqlite3.connect(str(path))
        conn.execute("INSERT INTO entities (qid, label, label_lower) VALUES ('Q49','North America','north america')")
        conn.execute("INSERT INTO claims (qid, property, value, value_qid) VALUES ('Q15','P31','continent',NULL)")
        conn.commit(); conn.close()
        wd = OfflineWikidata(db_path=str(path))
        # "located in Africa" should deny (P30 North America != Africa), not confirm via P463 African Bank
        d = wd.verify_triple("The USA", "is locate", "in Africa")
        assert d.result == VerificationResult.DENIED, f"expected denied via P30, got {d.result}"


# ── Router: possessive decomposition ────────────────────────────────────

class TestPossessiveDecomposition:
    def test_currency_possessive_denies(self, tmp_path):
        from src.resources.wikidata_offline import OfflineWikidata, VerificationResult
        from tests.test_five_way import _build_gate_fixture_db
        path = tmp_path / "poss.db"
        _build_gate_fixture_db(path,
            entities=[("Q30", "United States"), ("Q4917", "United States dollar")],
            claims=[("Q30", "P38", "United States dollar", "Q4917")],
            aliases=[("Q30", "usa")])
        wd = OfflineWikidata(db_path=str(path))
        assert wd._decompose_possessive("The USA's currency") == ("USA", "P38")
        assert wd._decompose_possessive("The currency of the USA") == ("USA", "P38")
        d = wd.verify_triple("The currency of the USA", "be", "the US dollar")
        assert d.result == VerificationResult.CONFIRMED


# ── Router: superlative gate ────────────────────────────────────────────

class TestSuperlativeGate:
    def test_largest_abstains_not_confirms(self, tmp_path):
        from src.resources.wikidata_offline import OfflineWikidata, VerificationResult
        from tests.test_five_way import _build_gate_fixture_db
        path = tmp_path / "superl.db"
        _build_gate_fixture_db(path,
            entities=[("Q30", "United States"), ("Q49", "North America")],
            claims=[("Q30", "P30", "North America", "Q49"), ("Q30", "P31", "country", None)],
            aliases=[])
        wd = OfflineWikidata(db_path=str(path))
        d = wd.verify_triple("The USA", "be", "the largest country in the world by land area")
        assert d.result == VerificationResult.UNKNOWN, f"superlative should abstain, got {d.result}"


# ── Router: location fallback blocker ───────────────────────────────────

class TestLocationBlocker:
    def test_chicago_capital_not_location_confirm(self, tmp_path):
        from src.resources.wikidata_offline import OfflineWikidata, VerificationResult
        from tests.test_five_way import _build_gate_fixture_db
        path = tmp_path / "loc.db"
        _build_gate_fixture_db(path,
            entities=[("Q30", "United States"), ("Q61", "Washington, D.C."), ("Q1297", "Chicago")],
            claims=[("Q30", "P36", "Washington, D.C.", "Q61"), ("Q1297", "P17", "United States", "Q30")],
            aliases=[("Q30", "usa")])
        wd = OfflineWikidata(db_path=str(path))
        # Chicago is in USA (P17), but "Chicago is The USA's capital" should deny via P36, not confirm via P17
        d = wd.verify_triple("Chicago", "be", "The USA 's capital")
        assert d.result == VerificationResult.DENIED
        assert d.property_id == "P36"
