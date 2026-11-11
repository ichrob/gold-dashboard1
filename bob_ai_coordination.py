"""Turn allowlisted Bob watchdog incidents into idempotent, public-safe AI handoffs.

Runs inside existing watchdog job, not a second paid service or LLM.
No model invocation, code execution, position change, or auto-merge.
"""
import os
import sys

from bob_issue_watchdog import CODES, issue_title, github_request, open_issue_rows

REPO = "ichrob/gold-dashboard1"
MARKER = "<!-- BOB_AI_HANDOFF_V1:"
MAX_PER_RUN = 3
# Diagnostic code only; never emit arbitrary issue text, logs or data.
HINTS = {
    "repair-watch-stalled": ("repair_supervision.py", "test_bob_self_healing.py"),
    "cfd-worker-stopped": ("auxiliary_workers.py", "test_auxiliary_repair.py"),
    "spot-change-worker-stopped": ("auxiliary_workers.py", "test_spot_daily_change.py"),
    "comparison-worker-stopped": ("auxiliary_workers.py", "test_comparison_health.py"),
    "trade-setup-stalled": ("trade_auto_monitor.py", "test_trade_workflow.py"),
    "screenshot-import-failed": ("handset_ocr_engine.py", "test_handset_ocr_engine.py"),
    "scanner-unreachable": ("server.py", "test_startup_health.py"),
    "scanner-degraded": ("runtime_watchdog.py", "test_runtime_watchdog.py"),
    "market-worker-stopped": ("auto_collection.py", "test_auto_collection.py"),
    "background-not-current": ("background_push.py", "test_background_health.py"),
    "research-worker-stopped": ("strategy_lab_background.py", "test_strategy_lab_daily.py"),
    "push-unreachable": ("push_server.py", "test_push_monitor.py"),
    "push-unhealthy": ("push_server.py", "test_push_delivery_evidence.py"),
    "paper-unhealthy": ("paper_health.py", "test_paper_health.py"),
    "study-original-input-degraded": ("research_restart.py", "test_bob_study_health.py"),
    "study-outcome-coverage-degraded": ("research_restart.py", "test_research_restart.py"),
    "study-worker-stale": ("paper_simulation.py", "test_bob_study_health.py"),
    "product-quote-evidence-missing": ("product_quotes.py", "test_product_quotes.py"),
    "product-leverage-clock-missing": ("product_data_quality.py", "test_product_data_quality.py"),
    "product-ko-validity-missing": ("product_data_quality.py", "test_product_data_quality.py"),
    "product-terms-evidence-missing": ("public_product_terms.py", "test_public_product_terms.py"),
}


def verified_cases(rows):
    """Only canonical known open health issues; never arbitrary public prose."""
    if not isinstance(rows, list):
        raise ValueError("invalid-issue-list")
    cases = {}
    titles = {issue_title(code): code for code in CODES}
    for row in rows:
        if not isinstance(row, dict) or row.get("state") != "open" or "pull_request" in row:
            continue
        code = titles.get(row.get("title"))
        number = row.get("number")
        author = row.get("user")
        if (code not in HINTS or type(number) is not int
                or not 1 <= number <= 99999999 or not isinstance(author, dict)
                or author.get("login") not in ("ichrob", "github-actions[bot]")):
            continue
        if code not in cases or number < cases[code]:
            cases[code] = number
    return sorted(((n, code) for code, n in cases.items()), key=lambda v: v[0])


def handoff(code, number):
    if code not in CODES or code not in HINTS or type(number) is not int:
        raise ValueError("invalid-case")
    source, test = HINTS[code]
    return (
        MARKER + code + " -->\n"
        "### Bob · KI-Reparaturübergabe (automatisch, nur öffentliche Fehlercodes)\n\n"
        "**Fall:** BOB-" + str(number) + "-" + code + "\n"
        "**Fehlerart:** " + CODES[code] + "\n"
        "**PR-Kennzeichnung:** Bei einem tatsächlichen Reparatur-PR die "
        "obige Fall-ID **genau einmal** in dessen Beschreibung angeben. "
        "Nur dann kann die optional freigeschaltete unabhängige Gemini- "
        "oder Cloudflare-Zweitprüfung den neuen Code sicher einem "
        "bekannten Bob-Fehlerfall zuordnen. Ohne echten PR kein Review.\n"
        "**Erster Code-Prüfpunkt:** " + source + "; möglicher Test: " + test + ".\n\n"
        "**ChatGPT-Reparaturwächter:** Originalursache anhand aktueller, berechtigter "
        "Diagnosen nachweisen; minimale Änderung als Pull Request mit Regressionstest "
        "vorschlagen. Kein PR oder Code-Fix ist hiermit bereits gestartet.\n\n"
        "**Zweit-KI:** Nach bereitgestelltem PR den begrenzten, unabhängigen "
        "Code-Review prüfen lassen, sofern kostenloser Anbieter verifiziert und "
        "explizit freigeschaltet ist. **Status bis zum echten Review-Beleg: "
        "nicht überprüft.** Ohne diese Voraussetzung kein KI-Aufruf.\n\n"
        "**Qualitätsschranke:** CI erfolgreich, unabhängige Prüfung, anschließend "
        "separater Live-Nachweis. Nicht automatisch als gelöst markieren. "
        "Originale, KO-/Produktnachweise und Handels- oder Risikoregeln "
        "nie aus einer KI-Antwort ableiten. Keine Orders.\n"
    )


def coordinate(*, token, repo, requester=github_request, limit=MAX_PER_RUN):
    if not token or repo != REPO or type(limit) is not int or not 1 <= limit <= MAX_PER_RUN:
        raise ValueError("configuration-denied")
    cases = verified_cases(open_issue_rows(token=token, repo=repo, requester=requester))
    added = 0
    for number, code in cases:
        if added >= limit:
            break
        comments = requester("GET", f"/issues/{number}/comments?per_page=100", token=token, repo=repo)
        if not isinstance(comments, list) or len(comments) >= 100:
            # Cannot verify completeness -> fail closed, never duplicate.
            continue
        marker = MARKER + code + " -->"
        if any(isinstance(x, dict) and isinstance(x.get("body"), str)
               and marker in x["body"] for x in comments):
            continue
        requester("POST", f"/issues/{number}/comments", token=token, repo=repo,
                  data={"body": handoff(code, number)})
        added += 1
    return added


def main():
    try:
        count = coordinate(token=os.environ.get("GITHUB_TOKEN"),
                           repo=os.environ.get("GITHUB_REPOSITORY"))
        print("Bob AI handoffs created: " + str(count))
    except Exception:
        # No raw headers, tokens, private diagnostic text or exception dumps.
        print("Bob AI handoff unavailable (watchdog remains independent).", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
