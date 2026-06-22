"""Smoke test (niente LLM) dell'eval analisi: i casi e i gold ci sono e sono ben formati.

Carica `evals/analysis/cases.py` via importlib dal path (robusto rispetto al packaging di
pytest), così il test gira nella suite senza dipendere da come `evals` è importabile.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CASES_PY = _ROOT / "evals" / "analysis" / "cases.py"
_GOLD = _ROOT / "evals" / "_shared" / "gold"


def _load_cases() -> list:
    spec = importlib.util.spec_from_file_location("evals_analysis_cases", _CASES_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CASES


def test_cases_non_empty_and_well_formed():
    cases = _load_cases()
    assert cases, "CASES non deve essere vuoto"
    for c in cases:
        assert {"name", "mode", "transcript", "expected"} <= set(c), f"chiavi mancanti in {c.get('name')}"
        assert c["transcript"].strip(), f"transcript vuoto in {c['name']}"
        exp = c["expected"]
        assert isinstance(exp["main_point"], str) and exp["main_point"].strip()
        assert isinstance(exp["must_capture"], list) and exp["must_capture"]
        assert isinstance(exp["must_not_invent"], list)


def test_every_case_has_valid_gold():
    for c in _load_cases():
        gold_path = _GOLD / f"{c.get('gold', c['name'])}.json"
        assert gold_path.exists(), f"manca il gold per {c['name']}"
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        assert "analysis" in gold and "questions" in gold, f"gold malformato per {c['name']}"
