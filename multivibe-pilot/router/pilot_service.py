"""Manage the resident pilot service for OpenCode.

  python pilot_service.py start    # control plane + quota refresh + router + edge
  python pilot_service.py stop
  python pilot_service.py status

The router keeps one account active until its 5-hour quota is nearly exhausted
(or upstream reports quota), then moves to the eligible account with the most
weekly quota left. Switch events are written for the OpenCode notifier plugin.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

DATA = pathlib.Path(os.environ['LOCALAPPDATA']) / 'MultiVibe-Codex-Pilot'
ROOT = pathlib.Path(__file__).resolve().parent
SECRETS_FILE = pathlib.Path(os.environ.get('PILOT_SECRETS_FILE', DATA / 'local-keys.json'))
LOCAL_CONFIG = json.loads(SECRETS_FILE.read_text())
KEYS = LOCAL_CONFIG
CONTAINER = 'multivibe-pilot-edge'
PID_FILE = DATA / 'pilot-service.pid'
STOP_FILE = DATA / 'pilot-service.stop'
SNAPSHOT = DATA / 'pilot-accounts.json'
LOG = DATA / 'pilot-service.log'
STATE = DATA / 'pilot-service-state.json'
CONTROL = 'http://127.0.0.1:1456'
REFRESH_INTERVAL = float(os.environ.get('PILOT_REFRESH_INTERVAL', '10'))


def accounts():
    configured = LOCAL_CONFIG.get('accounts')
    if configured:
        return configured
    return json.loads((DATA / 'accounts.json').read_text()).get('accounts', [])


def snapshot():
    SNAPSHOT.write_text(json.dumps({'accounts': accounts()}), encoding='utf-8')


def refresh_quota():
    request = urllib.request.Request(
        CONTROL + '/admin/usage/refresh', data=b'{}',
        headers={'Content-Type': 'application/json',
                 'x-admin-token': KEYS['admin']})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except Exception:
        return None


def port_open(port):
    import socket
    sock = socket.socket()
    try:
        return sock.connect_ex(('127.0.0.1', port)) == 0
    finally:
        sock.close()


def edge_ready():
    try:
        request = urllib.request.Request(
            'http://127.0.0.1:14755/v1/models',
            headers={'Authorization': 'Bearer ' + KEYS['proxy']})
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)
    except Exception:
        return None


def start_control_plane():
    subprocess.run([sys.executable, str(ROOT / 'start_pilot_control.py')],
                   capture_output=True, text=True, timeout=60)


def start_edge():
    subprocess.run(['docker', 'rm', '-f', CONTAINER], capture_output=True)
    env = os.environ.copy()
    env.update({'PROXY_API_KEY': KEYS['proxy'], 'ADMIN_TOKEN': KEYS['admin']})
    args = ['docker', 'run', '-d', '--rm', '--name', CONTAINER,
            '--cpus', '2', '--memory', '2g', '-p', '127.0.0.1:14755:14755',
            '--mount', 'type=volume,source=multivibe-review-target,target=/target,readonly',
            '--mount', f'type=bind,source={SNAPSHOT},target=/data/accounts.json',
            '-e', 'STORE_PATH=/data/accounts.json', '-e', 'V1_EDGE_HOST=0.0.0.0',
            '-e', 'V1_EDGE_PORT=14755', '-e', 'MAX_UPSTREAM_RETRIES=0',
            '-e', 'V1_EDGE_UPSTREAM_TIMEOUT_MS=90000', '-e', 'CODEX_SESSION_AFFINITY=true',
            '-e', 'CHATGPT_BASE_URL=http://host.docker.internal:14757',
            '-e', 'NODE_CONTROL_PLANE_URL=http://host.docker.internal:1456',
            '-e', 'PROXY_API_KEY', '-e', 'ADMIN_TOKEN',
            'rust:bookworm', '/target/debug/multivibe-v1-edge']
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise SystemExit('docker run failed: ' + (result.stderr or '').strip())


def pid_alive():
    try:
        pid = int(PID_FILE.read_text())
    except Exception:
        return False
    result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'],
                            capture_output=True, text=True)
    return str(pid) in result.stdout


def stop_all():
    STOP_FILE.write_text('stop', encoding='utf-8')
    if pid_alive():
        pid = PID_FILE.read_text().strip()
        subprocess.run(['taskkill', '/PID', pid, '/T', '/F'], capture_output=True)
    subprocess.run(['docker', 'stop', '-t', '3', CONTAINER], capture_output=True, timeout=30)
    try:
        control_pid = (DATA / 'control.pid').read_text().strip()
        subprocess.run(['taskkill', '/PID', control_pid, '/T', '/F'], capture_output=True)
    except Exception:
        pass
    try:
        STOP_FILE.unlink()
    except Exception:
        pass


def run():
    for stale in (STOP_FILE,):
        try:
            stale.unlink()
        except Exception:
            pass
    import pilot_router  # router policy + HTTP server
    pilot_router.serve()

    start_edge()
    for _ in range(60):
        if edge_ready() is not None:
            break
        time.sleep(0.5)
    else:
        raise SystemExit('edge did not become ready')
    last_refresh = 0.0
    try:
        while not STOP_FILE.exists():
            now = time.time()
            if now - last_refresh > REFRESH_INTERVAL:
                try:
                    refresh_quota()
                    pilot_router.router.reload()
                    pilot_router.router.ensure_active()
                    last_refresh = now
                    accounts_now = pilot_router.router.accounts
                    active = pilot_router.router.active
                    STATE.write_text(json.dumps({
                        'active': active + 1 if active is not None else None,
                        'accounts': [
                            {'n': i + 1, 'email': a.get('email'),
                             'primary_left': pilot_router.quota(a)['primary_left'],
                             'weekly_left': pilot_router.quota(a)['weekly_left'],
                             'enabled': a.get('enabled', True)}
                            for i, a in enumerate(accounts_now)
                        ],
                        'updated_at': int(now * 1000),
                    }, indent=2, ensure_ascii=False), encoding='utf-8')
                except Exception as error:
                    print('refresh loop error: ' + type(error).__name__ + ': ' + str(error), flush=True)
                    last_refresh = now
            time.sleep(2)
    finally:
        subprocess.run(['docker', 'stop', '-t', '3', CONTAINER], capture_output=True, timeout=30)


def start():
    stop_all()
    start_control_plane()
    refresh_quota()
    snapshot()
    log = LOG.open('a')
    creation = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    child = subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), 'run'],
                             stdout=log, stderr=subprocess.STDOUT,
                             creationflags=creation, close_fds=True)
    PID_FILE.write_text(str(child.pid))
    for _ in range(60):
        if child.poll() is not None:
            raise SystemExit('service exited; see ' + str(LOG))
        if port_open(14755) and port_open(14757) and edge_ready() is not None:
            print(json.dumps({'status': 'ready', 'pid': child.pid,
                              'proxy': 'http://127.0.0.1:14755/v1',
                              'state': status_payload()}, indent=2, ensure_ascii=False))
            return
        time.sleep(1)
    raise SystemExit('service did not become ready; see ' + str(LOG))


def status_payload():
    try:
        state = json.loads(STATE.read_text())
    except Exception:
        state = {}
    try:
        router_state = json.loads((DATA / 'pilot-router-state.json').read_text())
    except Exception:
        router_state = {}
    return {**state, 'router_active': router_state.get('active')}


def status():
    print(json.dumps({
        'running': port_open(14755) and pid_alive(),
        'pid_alive': pid_alive(),
        'edge_ready': edge_ready() is not None,
        'state': status_payload(),
    }, indent=2, ensure_ascii=False))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if action == 'start':
        start()
    elif action == 'run':
        run()
    elif action == 'stop':
        stop_all()
        print('stopped')
    elif action == 'status':
        status()
    else:
        raise SystemExit('usage: pilot_service.py start|stop|status')


if __name__ == '__main__':
    main()
