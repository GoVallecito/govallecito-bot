"""scripts/system_health.py: every broken link must exit 1 with a readable problem. Offline."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import system_health  # noqa: E402

OK_CHECKS = [{"id": "email-path", "label": "County alert email path (hourly canary)", "state": "OK", "detail": "fine"}]


def run(monkeypatch, tmp_path, *, smtp=(True, "sent"), fb=(True, "ok"), report=True, arrive=True,
        checks=None, public_ok=True):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(system_health.time, "sleep", lambda s: None)
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(system_health.time, "time", lambda: next(clock))
    monkeypatch.setattr(system_health, "send_canary", lambda nonce: smtp)
    monkeypatch.setattr(system_health, "facebook_check", lambda: fb)
    monkeypatch.setenv("LPC_TRIGGER_KEY", "k")
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    sent = {}

    def fake_http(url, data=None, timeout=20):
        if "__health-report" in url:
            if not report:
                raise OSError("down")
            sent["bot"] = json.loads(data)["bot"]
            return {"status": "OK", "checks": checks or OK_CHECKS, "canaryNonce": None}
        if url == system_health.PUBLIC_HEALTH:
            if not public_ok:
                raise OSError("route broken")
            return {"status": "OK"}
        nonce = "99-0" if arrive else "old"
        return {"status": "OK", "checks": checks or OK_CHECKS, "canaryNonce": nonce}

    monkeypatch.setattr(system_health, "_http", fake_http)
    code = system_health.main()
    return code, json.load(open(tmp_path / "health_result.json")), sent


def test_all_good(monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_ALERTS", "on")
    monkeypatch.setenv("DRY_RUN_VAR", "false")
    code, r, sent = run(monkeypatch, tmp_path)
    assert code == 0 and r["ok"] and r["problems"] == []
    assert sent["bot"] == {"fbOk": True, "fbDetail": "ok", "smtpOk": True, "siteAlerts": "on", "dryRun": "false"}


def test_canary_not_arriving(monkeypatch, tmp_path):
    code, r, _ = run(monkeypatch, tmp_path, arrive=False)
    assert code == 1 and any("canary email did not reach" in p for p in r["problems"])


def test_smtp_broken(monkeypatch, tmp_path):
    code, r, _ = run(monkeypatch, tmp_path, smtp=(False, "SMTP send failed: SMTPAuthenticationError"))
    assert code == 1 and any("Could not send the email canary" in p for p in r["problems"])


def test_worker_unreachable(monkeypatch, tmp_path):
    code, r, _ = run(monkeypatch, tmp_path, report=False, arrive=False)
    assert code == 1 and any("Could not reach the alerts Worker" in p for p in r["problems"])


def test_worker_reports_fail(monkeypatch, tmp_path):
    bad = [{"id": "facebook-token", "label": "Facebook Page token", "state": "FAIL", "detail": "HTTP 190"}]
    code, r, _ = run(monkeypatch, tmp_path, checks=bad)
    assert code == 1 and "Facebook Page token: HTTP 190" in r["problems"]


def test_public_route_broken(monkeypatch, tmp_path):
    code, r, _ = run(monkeypatch, tmp_path, public_ok=False)
    assert code == 1 and any("unreachable" in p for p in r["problems"])


def test_warn_is_not_a_failure(monkeypatch, tmp_path):
    warn = OK_CHECKS + [{"id": "regroup", "label": "LPC Alerts still emailing", "state": "WARN", "detail": "130 days ago"}]
    code, r, _ = run(monkeypatch, tmp_path, checks=warn)
    assert code == 0 and any(n.startswith("WARN") for n in r["notes"])


def test_missing_secrets_are_named(monkeypatch):
    for k in ("SMTP_USER", "SMTP_PASSWORD", "CANARY_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    ok, detail = system_health.send_canary("n")
    assert not ok and "SMTP_USER" in detail
