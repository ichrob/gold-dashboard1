"""Fail-closed, public-safe routing of failed MAIN GitHub workflows to Bob AI.

Runs from trusted default branch on completed workflow_run events only.
Never reads PR code, raw logs, private diagnostics, tokens, or model endpoints.
Creates at most one canonical incident per known failing workflow type.
A repaired runtime health check is NOT proof of CI/workflow recovery.
"""
import json
import os
import re
import sys

from bob_issue_watchdog import CODES, github_request, issue_title, open_issue_index

REPO = "ichrob/gold-dashboard1"
WORKFLOWS = {
    "Bob CI": "ci-main-failed",
    "Bob live smoke test": "smoke-main-failed",
    "Bob collection health": "collection-main-failed",
    "Bob independent self-healing escalation": "watchdog-main-failed",
}
ALLOWED_EVENTS = frozenset(("push", "schedule", "workflow_dispatch", "workflow_run"))
SHA = re.compile(r"[0-9a-f]{40}")


def verified_failure(event, *, repo=REPO):
    """Never trust workflow names, run URLs or descriptions outside the enum."""
    if not isinstance(event, dict) or repo != REPO:
        return None
    parent = event.get("repository")
    run = event.get("workflow_run")
    if (event.get("action") != "completed" or not isinstance(parent, dict)
            or parent.get("full_name") != REPO or not isinstance(run, dict)):
        return None
    head = run.get("head_repository")
    if not isinstance(head, dict):
        return None
    code = WORKFLOWS.get(run.get("name")) if type(run.get("name")) is str else None
    if (code not in CODES or run.get("status") != "completed"
            or run.get("conclusion") != "failure"
            or run.get("head_branch") != "main"
            or run.get("event") not in ALLOWED_EVENTS
            or head.get("full_name") != REPO):
        return None
    rid, sha = run.get("id"), run.get("head_sha")
    if (type(rid) is not int or not 1 <= rid <= 10**15
            or type(sha) is not str or not SHA.fullmatch(sha)):
        return None
    return {"code": code, "run": rid, "sha": sha}


def incident_body(record):
    """Only fixed code description, exact trusted SHA and numeric run ID."""
    code = record["code"]
    return (
        "### Bob · GitHub-Hauptprüfung fehlgeschlagen\n\n"
        "Code: " + code + " — " + CODES[code] + ".\n"
        "GitHub-Actions-Lauf: https://github.com/" + REPO
        + "/actions/runs/" + str(record["run"]) + "\n"
        "Commit: " + record["sha"] + "\n\n"
        "**Status: Fehler bestätigt, Ursache noch unbestimmt.** "
        "Dieser Lauf wurde von GitHub als fehlgeschlagen gemeldet. "
        "Keine privaten Logs oder Rohdaten sind in diesem Issue enthalten. "
        "Ein späterer erfolgreicher /health-Aufruf heilt diesen Vorfall NICHT.\n\n"
        "ChatGPT-Reparaturwächter: Nur nach vollständigem Ursachen-/Regressions-"
        "nachweis einen getrennten PR vorschlagen. Gemini: optionale unabhängige "
        "öffentliche Patchprüfung mit bestätigtem Free-only-Opt-in. "
        "Nach tatsächlichem PR, CI, Security und Render-Live-Abnahme "
        "gesondert als repariert kennzeichnen. Keine Orders, keine "
        "automatischen Merges, keine neuen Kosten."
    )


def route(record, *, token, repo=REPO, requester=github_request):
    if (not token or repo != REPO or not isinstance(record, dict)
            or record.get("code") not in WORKFLOWS.values()
            or type(record.get("run")) is not int
            or not 1 <= record["run"] <= 10**15
            or type(record.get("sha")) is not str
            or not SHA.fullmatch(record["sha"])):
        raise ValueError("untrusted-routing-input")
    title = issue_title(record["code"])
    found, duplicates = open_issue_index(token=token, repo=repo, requester=requester)
    if duplicates:
        # Never create a new issue if an existing index needs reconciliation.
        return "duplicates-need-reconciliation"
    if title in found:
        return "already-open"
    # A second complete index before creation prevents stale GitHub listings
    # from spawning duplicate incidents. Failure to retrieve is fatal/closed.
    again, duplicates = open_issue_index(token=token, repo=repo, requester=requester)
    if duplicates:
        return "duplicates-need-reconciliation"
    if title in again:
        return "already-open"
    issue = requester("POST", "/issues", token=token, repo=repo,
                      data={"title": title, "body": incident_body(record)})
    number = issue.get("number") if isinstance(issue, dict) else None
    if type(number) is not int or not 1 <= number <= 99999999:
        raise ValueError("issue-creation-unverified")
    # Existing coordinator recognizes this fixed code. The issue itself
    # remains available even if GitHub comment delivery subsequently fails.
    from bob_ai_coordination import handoff
    requester("POST", "/issues/" + str(number) + "/comments",
              token=token, repo=repo,
              data={"body": handoff(record["code"], number)})
    return "opened-" + str(number)


def main():
    try:
        if (os.environ.get("GITHUB_REPOSITORY") != REPO
                or os.environ.get("GITHUB_EVENT_NAME") != "workflow_run"
                or not os.environ.get("GITHUB_TOKEN")):
            raise ValueError("workflow-context-denied")
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not isinstance(event_path, str) or not event_path:
            raise ValueError("missing-event")
        with open(event_path, "rb") as stream:
            raw = stream.read(150001)
        if len(raw) > 150000:
            raise ValueError("oversized-event")
        failure = verified_failure(json.loads(raw))
        if not failure:
            print("No trusted failed main workflow; no incident created.")
            return
        outcome = route(failure, token=os.environ["GITHUB_TOKEN"])
        print("Bob AI GitHub failure routing: " + outcome)
    except Exception:
        # No raw HTTP errors or exception strings: they could include tokens.
        print("Bob AI failure routing unavailable; no recovery claimed.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
