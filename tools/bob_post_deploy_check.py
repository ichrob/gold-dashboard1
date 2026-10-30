"""Independent scheduled release observation, never a push-time Render gate.

Only public GitHub CI metadata and public read-only Render /health are used.
No API credentials are sent to Render; no private market or broker data.
"""
from datetime import datetime, timezone
import json
import os
import re
import sys
from urllib.request import Request, urlopen

from tools.bob_release_verify import HEALTH_URLS, SHA, read_health, verify

REPO = "ichrob/gold-dashboard1"
API = "https://api.github.com/repos/" + REPO
GRACE_SECONDS = 30 * 60
CI_RUNS_PER_PAGE = 5


def utc_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None


def classify(main_sha, ci_runs, scanner, push, now, grace_seconds=GRACE_SECONDS):
    """verified, pending or failed; no success for a stale or unknown SHA."""
    if not isinstance(main_sha, str) or SHA.fullmatch(main_sha) is None:
        return {"state": "failed", "reason": "invalid-main-sha"}
    matching = [r for r in (ci_runs if isinstance(ci_runs, list) else [])
                if isinstance(r, dict) and r.get("head_sha") == main_sha
                and r.get("event") == "push" and r.get("name") == "Bob CI"]
    if not matching:
        return {"state": "failed", "reason": "no-ci-evidence"}
    matching.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    ci = matching[0]
    success = ci.get("status") == "completed" and ci.get("conclusion") == "success"
    time_field = "updated_at" if success else "created_at"
    stamped = utc_time(ci.get(time_field))
    if stamped is None or not isinstance(now, datetime) or now.tzinfo is None:
        return {"state": "failed", "reason": "ci-time-unknown"}
    seconds = (now.astimezone(timezone.utc) - stamped).total_seconds()
    if seconds < -60:
        return {"state": "failed", "reason": "ci-time-in-future"}
    in_grace = -60 <= seconds <= grace_seconds
    if not success and ci.get("status") == "completed":
        return {"state": "failed", "reason": "ci-not-green"}
    if not success:
        return {"state": "pending" if in_grace else "failed",
                "reason": "ci-not-green"}
    both_ok, states = verify(main_sha, scanner, push)
    if both_ok:
        return {"state": "verified", "reason": "exact-healthy-builds", "services": states}
    return {"state": "pending" if in_grace else "failed",
            "reason": "build-or-health-unconfirmed", "services": states}


def github_json(path):
    # Restrict requests to the fixed GitHub repository API. Never print tokens.
    if not path.startswith("/") or "//" in path or ".." in path:
        raise ValueError("Invalid API path")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "bob-post-deploy-check", "Cache-Control": "no-store"}
    token = os.getenv("GH_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(API + path, headers=headers), timeout=20) as response:
        raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Oversized GitHub response")
        return json.loads(raw)


def read_ci_evidence():
    """Read only the few newest push runs needed for the current main SHA.

    A full 30-run Actions payload exceeds the deliberately small response cap.
    The endpoint is already restricted to main push runs, so five newest runs
    cover the current head and a small amount of deploy/CI overlap.
    """
    main_sha = github_json("/git/ref/heads/main")["object"]["sha"]
    ci_runs = github_json(
        "/actions/workflows/ci.yml/runs?branch=main&event=push&per_page="
        + str(CI_RUNS_PER_PAGE)
    )["workflow_runs"]
    return main_sha, ci_runs


def run(github_actions=False):
    checked = datetime.now(timezone.utc)
    try:
        main_sha, ci_runs = read_ci_evidence()
    except Exception as exc:
        result = {"state": "failed", "reason": "github-read-unavailable",
                  "errorType": type(exc).__name__}
    else:
        health = {}
        for name, url in HEALTH_URLS.items():
            try:
                health[name] = read_health(url)
            except Exception:
                health[name] = None
        result = classify(main_sha, ci_runs, health["scanner"], health["push"], checked)
        result["commit"] = main_sha[:12] if isinstance(main_sha, str) else "unknown"
    result["checkedAt"] = checked.isoformat()
    print(json.dumps(result, sort_keys=True))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("### Bob Post-Deploy (unabhängige Kontrolle)\n"
                         + "Status: **" + result["state"] + "**\n\n"
                         + "Grund: " + result["reason"] + "\n\n"
                         + "Prüfzeit UTC: " + result["checkedAt"] + "\n")
    # A scheduled observation can attach to a not-yet-deployed main commit.
    # It must not create a failing pre-deploy check for a bounded pending state.
    # The explicit output keeps all actual deployed-code tests skipped until
    # exact health/build verification succeeds. CLI pending remains nonzero.
    output_path = os.getenv("GITHUB_OUTPUT") if github_actions else None
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write("state=" + result["state"] + "\n")
    return {"verified": 0, "pending": 0 if github_actions else 2, "failed": 1}[result["state"]]


if __name__ == "__main__":
    sys.exit(run(github_actions="--github-actions" in sys.argv[1:]))
