"""Account router between the Rust edge and the real ChatGPT upstream.

Policy: keep the active account until its 5-hour quota is nearly exhausted
(<= THRESHOLD % left), then switch to the eligible account with the most
weekly quota left. A real upstream quota error also triggers an immediate
switch and one retry of the same request. Switch events are appended to
pilot-switch-events.jsonl for the OpenCode notifier plugin.

Never prints or logs credentials.
"""
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = pathlib.Path(os.environ['LOCALAPPDATA']) / 'MultiVibe-Codex-Pilot'
UPSTREAM = os.environ.get('CHATGPT_UPSTREAM', 'https://chatgpt.com')
THRESHOLD = float(os.environ.get('PILOT_SWITCH_THRESHOLD', '10'))
PORT = int(os.environ.get('PILOT_ROUTER_PORT', '14757'))
STATE = DATA / 'pilot-router-state.json'
EVENTS = DATA / 'pilot-switch-events.jsonl'
REQUESTS = DATA / 'pilot-router-requests.jsonl'


def load_accounts():
    for _ in range(3):
        try:
            store = json.loads((DATA / 'accounts.json').read_text())
            accounts = store.get('accounts', [])
            if accounts:
                return accounts
        except Exception:
            time.sleep(0.2)
    return []


def left(value):
    return None if value is None else max(0.0, 100.0 - float(value))


def quota(account):
    usage = account.get('usage') or {}
    primary = (usage.get('primary') or {}).get('usedPercent')
    weekly = (usage.get('secondary') or {}).get('usedPercent')
    return {
        'primary_left': left(primary),
        'weekly_left': left(weekly),
        'quotaStatus': usage.get('quotaStatus'),
    }


def eligible(account, threshold):
    if not account.get('enabled', True):
        return False
    if (account.get('state') or {}).get('reauthRequired'):
        return False
    q = quota(account)
    if q['weekly_left'] is None or q['weekly_left'] <= 0:
        return False
    if q['primary_left'] is None or q['primary_left'] <= threshold:
        return False
    return True


class Router:
    def __init__(self):
        self.lock = threading.Lock()
        self.accounts = []
        self.active = None
        self.reload()
        self._restore()
        if self.active is None:
            with self.lock:
                self._switch(None, self._best(), 'initial_selection')

    def reload(self):
        accounts = load_accounts()
        if accounts:
            self.accounts = accounts

    def _restore(self):
        try:
            state = json.loads(STATE.read_text())
            index = int(state.get('active'))
            if 0 <= index < len(self.accounts) and eligible(self.accounts[index], THRESHOLD):
                self.active = index
        except Exception:
            pass

    def _best(self, exclude=()):
        candidates = [i for i in range(len(self.accounts))
                      if i not in exclude and eligible(self.accounts[i], THRESHOLD)]
        if not candidates:
            return None
        return max(candidates, key=lambda i: (
            (quota(self.accounts[i])['weekly_left'] or 0),
            (quota(self.accounts[i])['primary_left'] or 0),
            -i))

    def _switch(self, old, new, reason):
        if new is None:
            return False
        self.active = new
        state = {'active': new, 'updated_at': int(time.time() * 1000)}
        try:
            STATE.write_text(json.dumps(state))
        except Exception:
            pass
        if old != new:
            event = {
                'ts': int(time.time() * 1000),
                'from': (old + 1) if old is not None else 0,
                'to': new + 1,
                'reason': reason,
                'from_primary_left': quota(self.accounts[old])['primary_left'] if old is not None else None,
                'from_weekly_left': quota(self.accounts[old])['weekly_left'] if old is not None else None,
                'to_primary_left': quota(self.accounts[new])['primary_left'],
                'to_weekly_left': quota(self.accounts[new])['weekly_left'],
            }
            if reason == 'initial_selection':
                event['reason_text'] = 'chọn tài khoản ban đầu'
            elif reason == 'upstream_quota':
                event['reason_text'] = 'upstream báo hết quota đột xuất'
            else:
                event['reason_text'] = f"quota 5 giờ còn {event['from_primary_left']:.0f}% (ngưỡng {THRESHOLD:.0f}%)"
            try:
                with EVENTS.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + '\n')
            except Exception:
                pass
        return True

    def ensure_active(self):
        """Switch before a request if the active account is near its 5h limit."""
        with self.lock:
            if self.active is None or self.active >= len(self.accounts):
                self.active = self._best()
                return self.active
            account = self.accounts[self.active]
            if eligible(account, THRESHOLD):
                return self.active
            best = self._best(exclude={self.active})
            if best is None:
                best = self._best()
            if best is not None and best != self.active:
                self._switch(self.active, best, 'threshold')
                return self.active
            return self.active

    def quota_error_switch(self):
        with self.lock:
            old = self.active
            candidates = [i for i in range(len(self.accounts))
                          if i != old and eligible(self.accounts[i], 0)]
            if not candidates:
                return None
            best = max(candidates, key=lambda i: (
                quota(self.accounts[i])['weekly_left'] or 0,
                quota(self.accounts[i])['primary_left'] or 0,
                -i))
            self._switch(old, best, 'upstream_quota')
            return best

    def current(self):
        with self.lock:
            if self.active is None:
                return None
            return self.accounts[self.active]


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        pass

    def _forward(self, body, account):
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ('host', 'connection', 'content-length',
                                        'accept-encoding', 'authorization',
                                        'chatgpt-account-id')}
        headers['Authorization'] = 'Bearer ' + account.get('accessToken', '')
        chatgpt_id = account.get('chatgptAccountId')
        if chatgpt_id:
            headers['chatgpt-account-id'] = chatgpt_id
        request = urllib.request.Request(
            UPSTREAM + self.path,
            data=body if self.command == 'POST' else None,
            headers=headers, method=self.command)
        return urllib.request.urlopen(request, timeout=90)

    def dispatch(self):
        if not self.path.startswith('/backend-api/codex/'):
            self.send_error(403)
            return
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        inference = self.command == 'POST' and self.path.endswith('/responses')
        attempts = 0
        while True:
            router.ensure_active()
            account = router.current()
            if account is None:
                payload = json.dumps({'error': {'type': 'quota_exhausted',
                                                'message': 'No pilot account has headroom'}}).encode()
                self.send_response(429)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(payload)
                return
            try:
                response = self._forward(body, account)
            except urllib.error.HTTPError as error:
                response = error
            except Exception:
                self.send_error(502, 'Upstream connection failed')
                return

            quota_failed = False
            if response.status == 429:
                try:
                    raw = response.read()
                except Exception:
                    raw = b''
                text = raw.decode('utf-8', 'replace')
                if 'usage_limit_reached' in text or 'usage limit' in text.lower() or 'quota' in text.lower():
                    quota_failed = True
                if quota_failed and inference and attempts < 2:
                    attempts += 1
                    new = router.quota_error_switch()
                    if new is not None:
                        continue
                self.send_response(response.status)
                if response.headers.get('Content-Type'):
                    self.send_header('Content-Type', response.headers['Content-Type'])
                self.end_headers()
                self.wfile.write(raw)
                return

            self.send_response(response.status)
            if response.headers.get('Content-Type'):
                self.send_header('Content-Type', response.headers['Content-Type'])
            if response.headers.get('Content-Encoding'):
                self.send_header('Content-Encoding', response.headers['Content-Encoding'])
            self.end_headers()
            try:
                read = getattr(response, 'read1', response.read)
                while True:
                    chunk = read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            if inference:
                try:
                    with REQUESTS.open('a', encoding='utf-8') as handle:
                        handle.write(json.dumps({
                            'ts': int(time.time() * 1000),
                            'account': router.active + 1 if router.active is not None else None,
                            'status': response.status,
                        }) + '\n')
                except Exception:
                    pass
            return

    do_GET = dispatch
    do_POST = dispatch


router = Router()


def serve():
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'PILOT_ROUTER_READY port={PORT} active={"None" if router.active is None else router.active + 1} threshold={THRESHOLD}', flush=True)
    return server


if __name__ == '__main__':
    server = serve()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
