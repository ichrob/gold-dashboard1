"""Local, operator-only one-click UI for a single licensed Twelve Data research request.

Never import from Bob startup, Render, Bob Handy, scheduler or public routes.
The browser sees *status only*, never vendor prices, dates or indicators.
This proof-of-control remains draft until independent runtime gates are signed off.
"""
import argparse
from html import escape
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import sqlite3
import stat
import time
from urllib.parse import parse_qs
import webbrowser

from twelve_research_extension import fetch_research, manual_preflight

SYMBOL = 'XAU/USD'
INTERVAL = '1h'
HISTORY_HOURS = 24
STEP_MS = 3_600_000
RELEASE_GATES = (
    'BOB_TWELVE_ONE_CLICK_RELEASE_APPROVED',
    'BOB_TWELVE_GLOBAL_QUOTA_EXCLUSIVE_VERIFIED',
    'BOB_TWELVE_CREDIT_WEIGHT_CONFIRMED',
    'BOB_TWELVE_DURABLE_RESEARCH_ARCHIVE_VERIFIED',
    'BOB_TWELVE_ERASURE_PLAN_VERIFIED',
    'BOB_TWELVE_RUNTIME_OAUTH_VERIFIED',
)
# Never set release flags in this module; each is an operator attestation,
# not independent evidence that a shared account/Drive/retention is safe.


def private_archive(path):
    """Require an existing non-symlink SQLite file in a private owned folder."""
    if not path or not os.path.isabs(path):
        return False
    try:
        path_stat = os.lstat(path)
        parent = os.lstat(os.path.dirname(path))
        return (
            stat.S_ISREG(path_stat.st_mode)
            and stat.S_ISDIR(parent.st_mode)
            and (path_stat.st_mode & 0o077) == 0
            and (parent.st_mode & 0o077) == 0
            and path_stat.st_uid == os.geteuid()
            and parent.st_uid == os.geteuid()
        )
    except (OSError, AttributeError, ValueError):
        return False


def readiness(env=None):
    """No API call and no database writes. Do not include key or archive path."""
    env = os.environ if env is None else env
    p = manual_preflight(SYMBOL, INTERVAL, env)
    blockers = [b for b in p['blockers'] if b != 'PERSISTENT_LEDGER_AND_RETENTION_UNVERIFIED']
    blockers += [name for name in RELEASE_GATES if env.get(name) != '1']
    if not private_archive(env.get('BOB_TWELVE_RESEARCH_ARCHIVE', '')):
        blockers.append('PRIVATE_PERSISTENT_ARCHIVE_NOT_VERIFIED')
    return {'code': 'BLOCKED' if blockers else 'READY_FOR_ONE_MANUAL_REQUEST',
            'blockers': blockers, 'manualOnly': True, 'networkUsed': False,
            'licensedDataDisplayed': False}


class OneClick:
    def __init__(self, env=None, *, clock=None, connect=None, fetch=None):
        self.env = os.environ if env is None else env
        self.clock = clock or time.time
        self.connect = connect or sqlite3.connect
        self.fetch = fetch or fetch_research
        self.used = False

    def run(self):
        """At most one attempt per UI session, including failed responses."""
        if self.used:
            return 'ALREADY_USED'
        check = readiness(self.env)
        if check['code'] != 'READY_FOR_ONE_MANUAL_REQUEST':
            return 'BLOCKED'
        self.used = True  # set BEFORE network activity or file opening
        now_ms = int(self.clock() * 1000)
        end_ms = (now_ms // STEP_MS) * STEP_MS
        start_ms = end_ms - HISTORY_HOURS * STEP_MS
        try:
            archive = self.env['BOB_TWELVE_RESEARCH_ARCHIVE']
            # No new ledger: use the existing adapter's atomic quota reservation.
            with self.connect(archive, timeout=10, isolation_level=None) as db:
                result = self.fetch(db, SYMBOL, INTERVAL, start_ms, end_ms,
                                    now_ms=now_ms)
            code = result.get('code', 'REQUEST_FAILED')
            # Only fixed, preapproved status codes ever reach the browser.
            return code if code in ('OBSERVED', 'NO_BARS', 'CREDIT_BUDGET_EXHAUSTED',
                                    'SCOPE_NOT_AUTHORIZED', 'KEY_NOT_CONFIGURED',
                                    'WORKER_COORDINATION_UNCONFIRMED',
                                    'PROVIDER_REJECTED', 'HTTP_ERROR',
                                    'NETWORK_ERROR', 'INVALID_RESPONSE',
                                    'RESPONSE_TOO_LARGE', 'INVALID_RANGE') else 'REQUEST_FAILED'
        except Exception:
            # No exception strings: they can contain keys, URLs, or identifiers.
            return 'REQUEST_FAILED'


def page(readiness_code, token, *, status=None, used=False):
    """No client scripts, data visualizations or real licensed observations."""
    label = ('Forschungsabruf starten' if not used
             else 'Einmaliger Abruf verbraucht')
    disabled = '' if readiness_code == 'READY_FOR_ONE_MANUAL_REQUEST' and not used else ' disabled'
    status_html = ('<p role="status">Status: ' + escape(status) + '</p>') if status else ''
    return ('''<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="referrer" content="no-referrer"><title>Bob – manuelle Forschung</title>
<style>body{font:18px system-ui;max-width:620px;margin:3rem auto;padding:1rem}
button{font:inherit;padding:1rem;border-radius:.6rem}p{line-height:1.5}</style>
</head><body><h1>Bob – Twelve Data Forschung</h1>
<p>Nur ein manueller interner XAU/USD-Abruf (1 Stunde, 24 abgeschlossene Stunden).
Keine Live-Kurse, Handelsdaten oder lizenzierten Ergebnisse auf dieser Seite.</p>
<p>Freigabe: ''' + escape(readiness_code) + '''</p>''' + status_html
            + '<form action="/run" method="post"><input type="hidden" name="nonce" value="'
            + escape(token, quote=True) + '"><button type="submit"' + disabled + '>'
            + escape(label) + '</button></form></body></html>')


def handler_factory(job, nonce):
    """Localhost-only, no GET side-effects; POST requires origin and CSRF token."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # never emit request headers, credentials or URL

        def send_page(self, status=None, code=200):
            body = page(readiness(job.env)['code'], nonce,
                        status=status, used=job.used).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy',
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def correct_host(self):
            return self.headers.get('Host') == ('127.0.0.1:' + str(self.server.server_port))

        def do_GET(self):
            if self.path != '/' or not self.correct_host():
                return self.send_page('NOT_FOUND', 404)
            self.send_page()

        def do_POST(self):
            expected = 'http://127.0.0.1:' + str(self.server.server_port)
            if (self.path != '/run' or not self.correct_host()
                    or self.headers.get('Origin') != expected
                    or self.headers.get('Content-Type') != 'application/x-www-form-urlencoded'):
                return self.send_page('DENIED', 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 256:
                    return self.send_page('DENIED', 403)
                data = parse_qs(self.rfile.read(length).decode('ascii'),
                                strict_parsing=True)
                supplied = data.get('nonce', [])
                if len(supplied) != 1 or not secrets.compare_digest(supplied[0], nonce):
                    return self.send_page('DENIED', 403)
            except (ValueError, UnicodeError):
                return self.send_page('DENIED', 403)
            self.send_page(job.run())
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Local manual-only research button')
    parser.add_argument('--serve', action='store_true', help='explicit localhost operator session')
    args = parser.parse_args()
    if not args.serve:
        parser.error('--serve is required; no background mode')
    job = OneClick()
    nonce = secrets.token_urlsafe(32)
    with HTTPServer(('127.0.0.1', 0), handler_factory(job, nonce)) as server:
        address = 'http://127.0.0.1:' + str(server.server_port) + '/'
        print('Lokaler Forschungsstart: ' + address)
        webbrowser.open(address)
        # A single consumed request ends the operator session. No idle server
        # or second submission remains after success OR provider failure.
        while not job.used:
            server.handle_request()


if __name__ == '__main__':
    main()
