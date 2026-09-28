"""
Hourly end-to-end health check for the emergency-alert system.

Run by .github/workflows/system-health.yml. Full design and the failure-mode matrix:
worker-lpcalerts/HEALTH.md in the SITE repo. In one run this:

  1. Emails a CANARY to alerts@govallecito.com from SMTP_USER (David's Gmail) with the
     secret CANARY_TOKEN in the subject. It travels the exact path an LPC Alert travels
     (MX -> Cloudflare Email Routing -> govallecito-lpcalerts Worker -> KV) and is then
     recognised and dropped by the Worker: never posted, never forwarded.
  2. Checks the Facebook Page token (scripts/wx/fb_preflight.py, GETs only).
  3. Reports that plus the two posting switches (SITE_ALERTS, DRY_RUN) to the Worker's
     /__health-report. The Worker adds its OWN check of the GitHub dispatch token and
     of the last emergency-alert run, stores it, and returns the full health verdict.
  4. Waits up to 5 minutes for THIS run's canary to show up in /data/health.json,
     which proves the email path end to end, right now.
  5. Also fetches the public https://govallecito.com/data/health.json (the URL the
     external UptimeRobot monitor watches) so a broken route is caught too.

Writes health_result.json and the job summary; exits 1 if anything is wrong. The
workflow turns that into a GitHub issue (email to David) and a healthchecks.io /fail
ping; recovery closes the issue. Standard library only, no new dependencies.
Secrets are never printed.
"""

import json
import os
import smtplib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from email.message import EmailMessage

PUBLIC_HEALTH = os.environ.get("HEALTH_URL", "https://govallecito.com/data/health.json")
WORKER_BASE = os.environ.get("LPC_WORKER_BASE", "https://govallecito-lpcalerts.dkontje.workers.dev")
CANARY_TO = os.environ.get("CANARY_TO", "alerts@govallecito.com")
UA = "govallecito-bot system-health"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _http(url, data=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Content-Type": "application/json"},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def send_canary(nonce):
    user, pw, token = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD"), os.environ.get("CANARY_TOKEN")
    if not (user and pw):
        return False, "SMTP_USER / SMTP_PASSWORD secrets not set"
    if not token or len(token) < 16:
        return False, "CANARY_TOKEN secret not set (or shorter than 16 chars)"
    msg = EmailMessage()
    msg["From"], msg["To"] = user, CANARY_TO
    msg["Subject"] = f"GV-CANARY {token} {nonce}"
    msg.set_content("Automated hourly health canary for the GoVallecito emergency-alert system. "
                    "Recognised and discarded by the govallecito-lpcalerts Worker. Never posted.")
    try:
        with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return True, f"sent from {user}"
    except Exception as exc:  # noqa: BLE001
        return False, f"SMTP send failed: {type(exc).__name__}"


def facebook_check():
    try:
        p = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "scripts", "wx", "fb_preflight.py")],
                           capture_output=True, text=True, timeout=90)
        lines = [l.strip() for l in (p.stdout + "\n" + p.stderr).splitlines() if l.strip()]
        detail = (lines[-1] if lines else "")[:180]
        return p.returncode == 0, detail or ("ok" if p.returncode == 0 else f"exit {p.returncode}")
    except Exception as exc:  # noqa: BLE001
        return False, f"preflight could not run: {type(exc).__name__}"


def post_report(bot):
    key = os.environ.get("LPC_TRIGGER_KEY", "")
    if not key:
        return None, "LPC_TRIGGER_KEY secret not set"
    url = f"{WORKER_BASE}/__health-report?key={urllib.request.quote(key)}"
    last = ""
    for attempt in range(3):
        try:
            return _http(url, json.dumps({"bot": bot}).encode("utf-8")), ""
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {getattr(exc, 'code', '')}"
            time.sleep(10 * (attempt + 1))
    return None, f"health report endpoint unreachable ({last})"


def main():
    problems, notes = [], []
    nonce = f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{int(time.time())}"

    smtp_ok, smtp_detail = send_canary(nonce)
    notes.append(f"canary: {smtp_detail}")
    if not smtp_ok:
        problems.append(f"Could not send the email canary: {smtp_detail}")

    fb_ok, fb_detail = facebook_check()
    bot = {"fbOk": fb_ok, "fbDetail": fb_detail, "smtpOk": smtp_ok,
           "siteAlerts": os.environ.get("SITE_ALERTS", ""), "dryRun": os.environ.get("DRY_RUN_VAR", "")}

    health, err = post_report(bot)
    if health is None:
        problems.append(f"Could not reach the alerts Worker: {err}")

    # Wait for THIS run's canary (Gmail -> MX -> Worker usually takes 10-60 s).
    arrived = False
    if smtp_ok:
        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                h = _http(f"{WORKER_BASE}/data/health.json")
                if h.get("canaryNonce") == nonce:
                    arrived, health = True, h
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(20)
        if not arrived:
            problems.append("This run's canary email did not reach the alerts Worker within 5 minutes "
                            "(Email Routing rule, Worker, KV, or CANARY_FROM != SMTP_USER).")

    # The public URL the external monitor watches (proves the govallecito.com route).
    try:
        pub = _http(PUBLIC_HEALTH)
        notes.append(f"public health.json: {pub.get('status')}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"Public {PUBLIC_HEALTH} unreachable: {type(exc).__name__} {getattr(exc, 'code', '')}")

    if health:
        for c in health.get("checks", []):
            if c.get("state") == "FAIL":
                problems.append(f"{c.get('label')}: {c.get('detail')}")
            elif c.get("state") == "WARN":
                notes.append(f"WARN {c.get('label')}: {c.get('detail')}")

    # De-duplicate (a stale canary shows both here and in the Worker's own check).
    seen, uniq = set(), []
    for p in problems:
        if p not in seen:
            seen.add(p)
            uniq.append(p)

    result = {"ok": not uniq, "problems": uniq, "notes": notes, "health": health}
    with open("health_result.json", "w") as f:
        json.dump(result, f, indent=2)

    lines = ["## Emergency alert system health: " + ("OK" if not uniq else "DEGRADED"), ""]
    lines += [f"- ❌ {p}" for p in uniq] + [f"- {n}" for n in notes]
    if health:
        lines += ["", "| Check | State | Detail |", "|---|---|---|"]
        lines += [f"| {c.get('label')} | {c.get('state')} | {c.get('detail')} |" for c in health.get("checks", [])]
    summary = "\n".join(lines)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary + "\n")
    return 0 if not uniq else 1


if __name__ == "__main__":
    sys.exit(main())
