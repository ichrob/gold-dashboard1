"""Independent, credentials-free service checks + GitHub issue escalation.

Invoked by scheduled GitHub Actions. Only fixed diagnostic codes and HTTP
availability are published to GitHub; no raw logs, headers, quote data, tokens,
trade IDs, names or provider error messages may enter the issue body.
"""
from datetime import datetime, timezone
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

APP = "https://bob-private-scanner.onrender.com"
PUSH = "https://bob-push-service.onrender.com"
ISSUE_TITLE = "[Bob KI-Hilfe] Ungelöste Gesundheitsstörung"
CODES = {
    "cfd-worker-stopped": "CFD-Abrufdienst läuft nicht",
    "spot-change-worker-stopped": "Spot-Tagesänderungsdienst läuft nicht",
    "comparison-worker-stopped": "Quellenvergleich läuft nicht",
    "trade-setup-stalled": "Automatische Trade-Einrichtung benötigt technische Prüfung",
    "screenshot-import-failed": "Screenshot-Erkennung benötigt technische Prüfung",
    "scanner-unreachable": "Bob-Webdienst nicht erreichbar",
    "scanner-degraded": "Markt-/Hintergrunddaten werden als beeinträchtigt gemeldet",
    "market-worker-stopped": "Marktdatensammlung läuft nicht",
    "background-not-current": "Trade-/Fibonacci-Überwachung nicht aktuell",
    "research-worker-stopped": "Täglicher Forschungs-Worker läuft nicht",
    "push-unreachable": "Push-/Datenbankdienst nicht erreichbar",
    "push-unhealthy": "Push-/Datenbank-Gesundheitsprüfung fehlgeschlagen",
    "paper-unhealthy": "Papierkonten-Hintergrundstatus beeinträchtigt",
    "product-quote-evidence-missing": "Emittentenkurse oder eigenständige Kurszeiten unvollständig",
    "product-leverage-clock-missing": "Emittentenhebel oder dessen eigener bzw. eindeutig gemeinsamer Zeitbezug fehlt",
    "product-ko-validity-missing": "KO-Wert oder dessen gültiger Datennachweis fehlt",
    "product-terms-evidence-missing": "Produktstammdaten oder zugehörige Nachweise unvollständig",
}

# Internal marker to avoid closing unresolved incidents on an unavailable
# private audit. This marker is NOT an issue type and is never published.
PRODUCT_AUDIT_UNKNOWN = "_private-product-audit-unavailable"
PRODUCT_CODES = frozenset(code for code in CODES if code.startswith("product-"))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def active_session(now=None):
    """Never interpret a market weekend pause as a failed trading worker."""
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Europe/Zurich"))
    return local.weekday() < 5 and 8 <= local.hour < 22


def decode(url, *, opener=urlopen):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Bob-independent-watchdog/1"})
    with opener(req, timeout=30) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("body too large")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("invalid document")
    return doc


def classify(app, background, push, *, market_open=True):
    """Never include raw, untrusted API strings or error details in the report."""
    errors = []
    if not isinstance(app, dict):
        errors.append("scanner-unreachable")
    else:
        if app.get("status") != "ok" and market_open:
            errors.append("scanner-degraded")
        assistance = app.get("assistanceCodes")
        if isinstance(assistance, list):
            errors.extend(code for code in assistance if isinstance(code, str) and code in ("trade-setup-stalled", "screenshot-import-failed"))
        pending = app.get('repairPendingCodes') or []
        if isinstance(pending,list):
            errors.extend(code for code in pending if isinstance(code,str) and code in CODES)
        auxiliary = app.get('auxiliaryWorkers') or {}
        if isinstance(auxiliary,dict):
            for code in ('cfd-worker-stopped','spot-change-worker-stopped','comparison-worker-stopped'):
                state=auxiliary.get(code) or {}
                if isinstance(state,dict) and state.get('running') is False:
                    errors.append(code)
        collection = app.get("automaticCollection")
        if market_open and isinstance(collection, dict) and (
            collection.get("enabled") is not True or collection.get("running") is not True
        ):
            errors.append("market-worker-stopped")
        research = app.get("strategyResearch")
        if market_open and isinstance(research, dict) and research.get("enabled") is True and research.get("running") is not True:
            errors.append("research-worker-stopped")
    if market_open and (not isinstance(background, dict) or background.get("status") != "ok"):
        errors.append("background-not-current")
    if not isinstance(push, dict):
        errors.append("push-unreachable")
    elif push.get("ok") is not True:
        errors.append("push-unhealthy")
    else:
        if market_open and 8 <= datetime.now(ZoneInfo("Europe/Zurich")).hour < 22:
            paper = push.get("paperObservation")
            if isinstance(paper, dict) and paper.get("state") not in ("ok", "warming"):
                errors.append("paper-unhealthy")
        if "productAuditCodes" in push:
            product_codes = push["productAuditCodes"]
            if not isinstance(product_codes, list):
                errors.append(PRODUCT_AUDIT_UNKNOWN)
            else:
                # Accept ONLY fixed diagnostic identifiers; never publish
                # arbitrary source errors, raw data or per-product values.
                errors.extend(code for code in product_codes if isinstance(code, str) and code in PRODUCT_CODES)
        else:
            errors.append(PRODUCT_AUDIT_UNKNOWN)
    return sorted(set(errors))


def probe(*, opener=urlopen, now=None):
    if not active_session(now):
        # A real outage remains relevant on weekends; avoid stale market-data
        # alerts while deliberately paused. Health endpoints are still tested.
        market_open = False
    else:
        market_open = True
    results = []
    for url in (APP + "/health", APP + "/health/background", PUSH + "/health"):
        try:
            results.append(decode(url, opener=opener))
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            results.append(None)
    return classify(*results, market_open=market_open)


def issue_body(codes, at):
    # The free public GitHub repository requires aggressively redacted reports.
    selected = sorted(set(code for code in codes if code in CODES))
    lines = "\n".join("- " + c + ": " + CODES[c] for c in selected)
    return (
        "## KI-Hilfe für Bob angefordert\n\n"
        "**Erkannt (UTC):** " + at + "\n\n"
        "**Unbestätigte / ungelöste Fehler:**\n" + lines + "\n\n"
        "**Was Bob bereits versucht hat:** Die öffentlichen Gesundheitsprüfungen "
        "stoßen bei gestoppten bekannten Workern kontrollierte, gedrosselte Neustarts an. "
        "Die unabhängige Prüfung wurde nach einer Wartefrist wiederholt und meldet weiter einen Fehler.\n\n"
        "**Arbeitsauftrag an die KI:** Den betroffenen Dienst sowie GitHub-Actions- und "
        "Render-Logs auf Ursachen prüfen. Fix mit Regressionstests implementieren und "
        "prüfen, bevor der produktive Code geändert wird. Keine Trades ausführen, keine "
        "Strategie-/Risikoregeln eigenmächtig ändern.\n\n"
        "Diese Meldung enthält bewusst keine Secrets, persönlichen Daten, Rohlogs oder "
        "Produkt-/Handelsinformationen. Diese GitHub-Issue ist in einem öffentlichen Repository sichtbar."
    )


def github_request(method, api_path, *, token, repo, data=None, opener=urlopen):
    url = "https://api.github.com/repos/" + repo + api_path
    encoded = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(url, data=encoded, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "Bob-independent-watchdog/1",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with opener(request, timeout=25) as response:
        raw = response.read(200001)
    if len(raw) > 200000:
        raise ValueError("GitHub response too large")
    return json.loads(raw) if raw else {}


def issue_title(code):
    """Stable, allowlisted issue identity: one open issue per fault category."""
    if code not in CODES:
        raise ValueError("Unbekannter Fehlercode")
    return "[Bob KI-Hilfe] " + code


def sync_issue(codes, *, token, repo, at=None, requester=github_request):
    """Keep individual open GitHub problems in sync with confirmed health faults.

    The public issue list is only an incident index, not a source of raw logs.
    Only infrastructure faults automatically close after verified recovery.
    Product proof incidents require original-source confirmation and explicit
    review. Missing diagnostic codes are not evidence of recovery.
    """
    if not token or repo != "ichrob/gold-dashboard1":
        raise ValueError("GitHub-Umgebung nicht freigegeben")
    at = at or utc_now()
    issues = requester("GET", "/issues?state=open&per_page=100", token=token, repo=repo)
    if not isinstance(issues, list):
        raise ValueError("Issue-Liste ungültig")
    indexed = {
        row["title"]: row["number"]
        for row in issues
        if isinstance(row, dict) and "pull_request" not in row
        and isinstance(row.get("number"), int)
        and (row.get("title") == ISSUE_TITLE or row.get("title") in
             {issue_title(code) for code in CODES})
    }
    detected = sorted(set(code for code in codes if code in CODES))
    # This public watchdog sees only anonymous error codes. It cannot verify
    # the underlying broker or issuer records, so never auto-close product issues.
    product_titles = {issue_title(code) for code in PRODUCT_CODES | {"trade-setup-stalled", "screenshot-import-failed"}}
    actions = []

    # First create any missing problem; each fault maps to precisely one open
    # help request. No copies of private runtime logs are ever published.
    for code in detected:
        title = issue_title(code)
        if title in indexed:
            continue
        result = requester("POST", "/issues", token=token, repo=repo,
                           data={"title": title, "body": issue_body([code], at)})
        actions.append("opened-" + str(result.get("number", "?")))

    # Keep incidents open while failing, even if the user opened/read them.
    # Close only those problem categories that are now independently healthy.
    for title, number in indexed.items():
        if title != ISSUE_TITLE and title in {issue_title(code) for code in detected}:
            continue
        if title in product_titles:
            # A disappearing error code (or unavailable audit) cannot prove
            # source validity. Closure requires separately confirmed evidence.
            continue
        if title == ISSUE_TITLE and not detected:
            # Compatibility with old combined issue title.
            message = "Neue Einzelprobleme oder normalisierte Dienste; historischer Sammelbericht geschlossen."
        elif title == ISSUE_TITLE:
            message = "Durch einzeln gezählte KI-Hilfeanfragen ersetzt. Diese Sammelmeldung bleibt archiviert."
        else:
            message = "Unabhängige Nachprüfung: Diese Fehlerart ist nicht mehr aktiv."
        requester("POST", "/issues/" + str(number) + "/comments", token=token, repo=repo,
                  data={"body": message + " Stand: " + at + " UTC."})
        requester("PATCH", "/issues/" + str(number), token=token, repo=repo,
                  data={"state": "closed"})
        actions.append("closed-" + str(number))
    if actions:
        return ",".join(actions)
    if PRODUCT_AUDIT_UNKNOWN in codes:
        return "audit-unavailable"
    return "already-open" if detected or any(t in product_titles for t in indexed) else "healthy"


def main():
    # Two consecutive independent polls prevent a single slow request or cold
    # start from generating an incident. /health performs only safe worker restarts.
    first = probe()
    if first:
        time.sleep(15)
        second = probe()
    else:
        second = []
    detected = second
    at = utc_now()
    print("BOB_WATCHDOG at=" + at + " codes=" + ",".join(detected or ["healthy"]), flush=True)
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("No GitHub issue token; local diagnostic mode only", flush=True)
        return 1 if any(code in CODES for code in detected) else 0
    result = sync_issue(detected, token=token, repo=repo, at=at)
    print("BOB_WATCHDOG issue=" + result, flush=True)
    return 1 if any(code in CODES for code in detected) else 0


if __name__ == "__main__":
    sys.exit(main())
