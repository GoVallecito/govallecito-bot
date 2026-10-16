from scripts.wx import review_panel as RP


def _rep(monkeypatch, strict):
    if strict:
        monkeypatch.setenv("WX_PANEL_STRICT_EDITOR", "true")
    else:
        monkeypatch.delenv("WX_PANEL_STRICT_EDITOR", raising=False)
    obj = {"verdict": "issues", "issues": [
        {"severity": "major", "quote": "x", "problem": "reuses opener",
         "evidence": "", "fix": ""}]}
    return RP._normalize_report(obj, "editor")


def test_editor_major_is_advisory_by_default(monkeypatch):
    assert _rep(monkeypatch, False)["issues"][0]["severity"] == "minor"


def test_strict_flag_restores_major(monkeypatch):
    assert _rep(monkeypatch, True)["issues"][0]["severity"] == "major"


def test_fact_checker_unaffected(monkeypatch):
    monkeypatch.delenv("WX_PANEL_STRICT_EDITOR", raising=False)
    obj = {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": "x", "problem": "bad number",
         "evidence": "no", "fix": ""}]}
    assert RP._normalize_report(obj, "fact checker")["issues"][0]["severity"] == "critical"
