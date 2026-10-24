"""Bob – Handy: authenticated, passive HTTPS-to-Android link handoff.

No private messages, commands, sessions, account data, tokens or remote orders are
stored/served. A browser button opens an existing Android custom deep link. Even
if Android resolves it, the phone still requires fresh explicit local consent.
This is NOT a verified Android App Link or automatic ChatGPT remote control.
"""
from html import escape

PAGES = {
    "OPEN_BOB": ("Bob öffnen", "overview"),
    "OPEN_PRODUCTS": ("Gold-Hebelprodukte anzeigen", "products"),
    "OPEN_MARKET": ("Goldmarkt anzeigen", "overview"),
    "OPEN_TRADE": ("Mein Trade anzeigen", "trade"),
    "OPEN_SIMULATION": ("Simulationen anzeigen", "simulation"),
    "OPEN_LEARNING": ("Lernergebnisse anzeigen", "learning"),
    "OPEN_RESEARCH": ("Gold-Recherche anzeigen", "research"),
    "OPEN_LONG_REVIEW": ("LONG-Produkte vergleichen", "products-long"),
    "OPEN_LEVERAGE_REVIEW": ("Hebelrisiken erklären", "products-leverage"),
}


def route(path, query=""):
    """Exact Bob view with the fixed ChatGPT link attribution marker only.

    Every other query, including multiple or encoded parameters, is denied.
    """
    if query not in ("", "utm_source=chatgpt.com") or not isinstance(path, str):
        return None
    prefix = "/handy/"
    if not path.startswith(prefix):
        return None
    command = path[len(prefix):]
    if command not in PAGES or path != prefix + command:
        return None
    return command


def render_page(command):
    """Static, allowlisted and data-free HTML. Never auto-launch an app."""
    label, view = PAGES[command]
    safe_title = escape(label)
    custom_uri = "bobhandy://handoff/" + command
    web_fallback = "/?view=" + view + "#" + view
    page = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bob – Handy: Auftrag prüfen</title>
<style>
:root{color-scheme:light}
body{font:17px/1.55 system-ui,sans-serif;max-width:590px;margin:36px auto;
padding:0 22px;color:#172638;background:#fff}
a.action{display:block;text-align:center;background:#125fb6;color:#fff;
border-radius:12px;padding:16px;margin:18px 0;font-weight:700;text-decoration:none}
a.backup{display:block;text-align:center;color:#125fb6;padding:12px}
.note{border:1px solid #bbc9d8;border-radius:12px;padding:15px;margin:20px 0}
small{color:#43566d}
</style>
</head>
<body>
<h1>Bob – Handy</h1>
<p><strong>Vorgeschlagene Anzeige:</strong> TITLE</p>
<p>Du kannst die Anzeige jetzt in deiner Android-App vorbereiten.
In <strong>„Bob – Handy“</strong> musst du sie anschließend
ausdrücklich einmalig erlauben.</p>
<a class="action" href="APP_URI">Bob – Handy öffnen</a>
<a class="backup" href="FALLBACK">Stattdessen Bob im Browser öffnen</a>
<div class="note"><strong>Sicherheitsgrenze:</strong> Dieser Link gibt keine
Fernberechtigung und löst selbst keine Aktion aus. Er überträgt keine
Zugangsdaten oder Depotinformationen. Keine DEGIRO-Bedienung oder Echtgeldorder.
Falls Android nach der App fragt, nur „Bob – Handy“ wählen.</div>
<small>Die Bob-Anmeldung bleibt erforderlich. Die App-Freigabe verfällt
nach 60 Sekunden, bei STOPP oder beim App-Wechsel.</small>
</body>
</html>"""
    return (page.replace("TITLE", safe_title)
                .replace("APP_URI", custom_uri)
                .replace("FALLBACK", web_fallback)).encode("utf-8")


def send(handler, command, head=False):
    body = render_page(command)
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if not head:
        handler.wfile.write(body)
