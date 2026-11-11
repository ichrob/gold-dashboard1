"""Local Bob Handy ACP client. No cloud relay, API-key fallback, or shell endpoint.

Started only by a local signed-app tap. The loopback bearer is ephemeral and is
never logged. ACP owns execution/credentials; its permission requests are shown
in Bob Handy and require one-shot decisions. Unadvertised client tools fail closed.
"""
from __future__ import annotations

import argparse
from collections import deque
import fcntl
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

MAX_BODY = 32768
MAX_LINE = 1048576
SESSION_SECONDS = 7200
HEARTBEAT_SECONDS = 120
OWNER_CONTEXT = (
    'Du arbeitest eigenständig für den Besitzer an Bob, ohne ChatGPT. '
    'Lies GEMINI.md und BOB_LOCAL_ACCESS.md, sofern vorhanden. '
    'Arbeite im eigenen Branch, berücksichtige parallele Reparaturen, führe passende Tests aus '
    'und belege Änderungen mit Commit/PR und tatsächlichen Testergebnissen. '
    'Keine Echtgeldorders, keine kostenpflichtigen Ressourcen oder API-Fallbacks, '
    'keine Geheimnisse ausgeben oder veröffentlichen. Bestehende Nutzerfreigaben gelten '
    'nur für den konkreten Auftrag. Ein CI-Erfolg beweist keinen produktiven Erfolg. '
    'Zugänge müssen tatsächlich funktionieren; erfinde keine Verbindungen. '
    'Antworte auf Deutsch. Auftrag des Besitzers:\n'
)


class Bridge:
    def __init__(self, workspace: Path, executable: Path):
        self.workspace, self.executable = workspace, executable
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.proc = None
        self.session = None
        self.seq = 0
        self.pending = {}
        self.permissions = {}
        self.events = deque(maxlen=200)
        self.event_seq = 0
        self.state = 'starting'
        self.closed = False
        self.born = self.touched = time.monotonic()
        self.first_prompt = True

    def event(self, kind, text):
        with self.lock:
            self.event_seq += 1
            self.events.append({'id': self.event_seq, 'kind': kind, 'text': str(text)[:12000]})
            while sum(len(e['text']) for e in self.events) > 120000:
                self.events.popleft()

    def send(self, message):
        with self.write_lock:
            if not self.proc or self.proc.poll() is not None:
                raise RuntimeError('AGENT_NOT_RUNNING')
            self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()

    def rpc(self, method, params, timeout=60):
        with self.lock:
            self.seq += 1
            rid = self.seq
            entry = {'event': threading.Event()}
            self.pending[rid] = entry
        try:
            self.send({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params})
            if not entry['event'].wait(timeout):
                raise RuntimeError('AGENT_TIMEOUT')
            reply = entry.get('reply', {})
            if 'error' in reply:
                code = reply['error'].get('code')
                raise RuntimeError('LOGIN_REQUIRED' if code == -32000 else 'AGENT_REQUEST_FAILED')
            return reply.get('result', {})
        finally:
            with self.lock:
                self.pending.pop(rid, None)

    def start(self):
        try:
            with self.lock:
                if self.closed:
                    return
            # No API-key/billing fallback is passed to the agent. Personal cached
            # Antigravity login remains in Termux; the app never reads credentials.
            env = {k: v for k, v in os.environ.items() if k not in (
                'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS',
                'GOOGLE_GENAI_USE_VERTEXAI', 'GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION')}
            env['PATH'] = str(self.executable.parent) + os.pathsep + env.get('PATH', '')
            self.proc = subprocess.Popen(
                [str(self.executable), 'acp'], cwd=self.workspace, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', start_new_session=True, bufsize=1)
            if self.closed:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=2)
                return
            threading.Thread(target=self.read_loop, daemon=True).start()
            init = self.rpc('initialize', {'protocolVersion': 1, 'clientCapabilities': {},
                           'clientInfo': {'name': 'bob-handy', 'version': '1.0'}})
            if init.get('protocolVersion') != 1:
                raise RuntimeError('ACP_VERSION_UNSUPPORTED')
            result = self.rpc('session/new', {'cwd': str(self.workspace), 'mcpServers': []})
            if not isinstance(result.get('sessionId'), str) or not result['sessionId']:
                raise RuntimeError('ACP_SESSION_MISSING')
            with self.lock:
                if self.closed:
                    return
                self.session = result['sessionId']
                self.state = 'ready'
            self.event('status', 'Gemini verbunden. Du kannst deinen Bob-Auftrag eingeben.')
        except Exception as exc:
            code = str(exc) if str(exc) in {
                'LOGIN_REQUIRED', 'AGENT_TIMEOUT', 'ACP_VERSION_UNSUPPORTED',
                'ACP_SESSION_MISSING', 'AGENT_REQUEST_FAILED'} else 'AGENT_START_FAILED'
            self.event('error', code)
            self.stop()

    def read_loop(self):
        try:
            while not self.closed:
                line = self.proc.stdout.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    raise ValueError('oversized ACP frame')
                msg = json.loads(line)
                self.receive(msg)
        except Exception:
            self.event('error', 'AGENT_CONNECTION_LOST')
        finally:
            with self.lock:
                for entry in self.pending.values():
                    entry['reply'] = {'error': {'code': -32603}}
                    entry['event'].set()
            if not self.closed:
                self.event('error', 'AGENT_EXITED')
                self.stop()

    def receive(self, msg):
        if not isinstance(msg, dict):
            raise ValueError('invalid ACP frame')
        method, rid = msg.get('method'), msg.get('id')
        if not method:
            with self.lock:
                entry = self.pending.get(rid)
                if entry:
                    entry['reply'] = msg
                    entry['event'].set()
            return
        params = msg.get('params', {})
        if not isinstance(params, dict):
            raise ValueError('invalid params')
        if method == 'session/request_permission' and rid is not None:
            with self.lock:
                valid_session = self.session and params.get('sessionId') == self.session
                if self.closed or self.state != 'running' or not valid_session:
                    self.send({'jsonrpc': '2.0', 'id': rid, 'result': {'outcome': {'outcome': 'cancelled'}}})
                    return
                # Never offer persistent/global approval from the phone UI.
                options = [o for o in params.get('options', []) if isinstance(o, dict)
                           and o.get('kind') in ('allow_once', 'reject_once')
                           and isinstance(o.get('optionId'), str)]
                if not options or len(self.permissions) >= 8:
                    self.send({'jsonrpc': '2.0', 'id': rid, 'result': {'outcome': {'outcome': 'cancelled'}}})
                    return
                key = os.urandom(16).hex()
                call = params.get('toolCall', {})
                details = json.dumps(call, ensure_ascii=False, indent=2)
                # A truncated command must never receive an allow button.
                if len(details) > 16000:
                    options = [o for o in options if o.get('kind') == 'reject_once']
                    details = 'Aufruf zu groß für eine vollständige Prüfung. Bitte ablehnen.'
                self.permissions[key] = {'rpcId': rid, 'options': options,
                                         'details': details, 'at': time.monotonic()}
            return
        if method == 'session/update':
            if self.session and params.get('sessionId') != self.session:
                return
            update = params.get('update', {})
            kind = update.get('sessionUpdate')
            if kind == 'agent_message_chunk':
                content = update.get('content', {})
                if content.get('type') == 'text':
                    self.event('answer', content.get('text', ''))
            elif kind in ('tool_call', 'tool_call_update'):
                self.event('tool', str(update.get('title', 'Werkzeug')) + ' · ' + str(update.get('status', '')))
            return
        if rid is not None:
            self.send({'jsonrpc': '2.0', 'id': rid, 'error': {'code': -32601,
                       'message': 'Client capability not supported'}})

    def prompt(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000 or '\x00' in text:
            raise ValueError('INVALID_PROMPT')
        with self.lock:
            if self.closed or self.state != 'ready':
                raise ValueError('NOT_READY')
            self.state = 'running'
            first = self.first_prompt
            self.first_prompt = False
        self.event('user', text)
        threading.Thread(target=self._prompt, args=((OWNER_CONTEXT if first else '') + text,), daemon=True).start()

    def _prompt(self, text):
        try:
            result = self.rpc('session/prompt', {'sessionId': self.session,
                              'prompt': [{'type': 'text', 'text': text}]}, timeout=1800)
            reason = result.get('stopReason', 'unknown')
            self.event('status', 'Gemini-Auftrag beendet: ' + str(reason) + '. Ergebnis und Tests prüfen.')
        except Exception as exc:
            self.event('error', str(exc) if str(exc) in {'AGENT_TIMEOUT', 'LOGIN_REQUIRED'} else 'AGENT_REQUEST_FAILED')
            # A timeout is not proof the agent stopped. End its process group.
            self.stop()
        finally:
            with self.lock:
                self.reject_all()
                if not self.closed:
                    self.state = 'ready'

    def permission(self, key, option):
        with self.lock:
            item = self.permissions.get(key)
            if not item or self.closed or time.monotonic() - item['at'] > 300:
                raise ValueError('PERMISSION_EXPIRED')
            if option not in [o['optionId'] for o in item['options']]:
                raise ValueError('INVALID_PERMISSION')
            self.send({'jsonrpc': '2.0', 'id': item['rpcId'],
                       'result': {'outcome': {'outcome': 'selected', 'optionId': option}}})
            del self.permissions[key]

    def reject_all(self):
        for item in list(self.permissions.values()):
            try:
                self.send({'jsonrpc': '2.0', 'id': item['rpcId'],
                           'result': {'outcome': {'outcome': 'cancelled'}}})
            except Exception:
                pass
        self.permissions.clear()

    def stop(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.state = 'stopped'
            self.reject_all()
            proc = self.proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=2)
            except ProcessLookupError:
                pass

    def snapshot(self):
        with self.lock:
            self.touched = time.monotonic()
            return {'state': self.state, 'events': list(self.events),
                    'permissions': [{'id': k, 'details': v['details'],
                                     'options': [{'id': o['optionId'], 'kind': o['kind']} for o in v['options']]}
                                    for k, v in self.permissions.items()],
                    'remainingSeconds': max(0, int(SESSION_SECONDS - (time.monotonic() - self.born)))}


def handler_for(bridge, token, port):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass

        def authorized(self):
            # No browser origin/CORS, no URL credentials, no DNS rebinding.
            return (self.client_address[0] == '127.0.0.1'
                    and self.headers.get('Host') == f'127.0.0.1:{port}'
                    and not self.headers.get('Origin')
                    and hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token))

        def reply(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.authorized():
                return self.reply(403, {'error': 'FORBIDDEN'})
            if self.path != '/status':
                return self.reply(404, {'error': 'NOT_FOUND'})
            self.reply(200, bridge.snapshot())

        def do_POST(self):
            if not self.authorized():
                return self.reply(403, {'error': 'FORBIDDEN'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('INVALID_BODY')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('INVALID_BODY')
                if self.path == '/prompt':
                    bridge.prompt(body.get('text'))
                elif self.path == '/permission':
                    bridge.permission(body.get('id'), body.get('option'))
                elif self.path == '/stop':
                    bridge.stop()
                else:
                    return self.reply(404, {'error': 'NOT_FOUND'})
                self.reply(200, {'accepted': True})
            except (ValueError, TypeError, KeyError):
                self.reply(400, {'error': 'REQUEST_REJECTED'})
            except Exception:
                self.reply(503, {'error': 'AGENT_UNAVAILABLE'})
    return Handler


def serve(port, token):
    if not 20000 <= port <= 60000 or not re.fullmatch('[0-9a-f]{64}', token):
        raise ValueError('invalid local session')
    home = Path.home()
    workspace = home / 'bob-gemini-work'
    executable = home / '.local/bin/agy'
    # Never choose an arbitrary directory or execute remote-provided commands.
    if not workspace.is_dir() or not (workspace / '.git').exists() or not executable.is_file():
        raise RuntimeError('WORKSPACE_OR_AGENT_MISSING')
    origin = subprocess.check_output(['git', '-C', str(workspace), 'remote', 'get-url', 'origin'],
                                     text=True, timeout=5).strip()
    if origin not in ('https://github.com/ichrob/gold-dashboard1.git', 'https://github.com/ichrob/gold-dashboard1'):
        raise RuntimeError('WRONG_REPOSITORY')
    lockdir = home / '.cache'
    lockdir.mkdir(mode=0o700, exist_ok=True)
    with open(lockdir / 'bob-gemini-bridge.lock', 'w') as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        bridge = Bridge(workspace, executable)
        server = ThreadingHTTPServer(('127.0.0.1', port), handler_for(bridge, token, port))
        server.daemon_threads = True
        server.timeout = 1
        threading.Thread(target=bridge.start, daemon=True).start()
        try:
            stopped_at = None
            while True:
                server.handle_request()
                if bridge.closed:
                    stopped_at = stopped_at or time.monotonic()
                    if time.monotonic() - stopped_at > 15:
                        break
                now = time.monotonic()
                if now - bridge.born > SESSION_SECONDS or now - bridge.touched > HEARTBEAT_SECONDS:
                    bridge.stop()
                    break
                with bridge.lock:
                    expired = any(now - p['at'] > 300 for p in bridge.permissions.values())
                    if expired:
                        bridge.reject_all()
        finally:
            bridge.stop()
            server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    try:
        serve(args.port, args.token)
    except Exception:
        # Do not print argv, credentials, agent diagnostics or private paths.
        print('BOB_GEMINI_START_FAILED')
        raise SystemExit(1)
