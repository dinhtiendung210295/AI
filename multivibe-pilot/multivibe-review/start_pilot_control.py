"""Start only the isolated Node control plane (no inference, no Docker).

Used for read-only quota refresh before the real failover harness. Keeps the
same private data directory and environment as `start_login_pilot.py`, but
does not start the Rust edge container and does not touch the live Codex
config. Never prints credentials.
"""
import json, os, pathlib, socket, subprocess, sys, time, urllib.request

root = pathlib.Path(__file__).resolve().parent
data = pathlib.Path(os.environ['LOCALAPPDATA']) / 'MultiVibe-Codex-Pilot'
keys_path = data / 'local-keys.json'
if not (data / 'accounts.json').exists() or not keys_path.exists():
    raise SystemExit('pilot data missing; run start_login_pilot.py once first')
keys = json.loads(keys_path.read_text())


def healthy():
    try:
        urllib.request.urlopen('http://127.0.0.1:1456/health', timeout=1).close()
        return True
    except Exception:
        return False


def port_free(port):
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


if healthy():
    print('CONTROL_PLANE_ALREADY_RUNNING 127.0.0.1:1456')
    raise SystemExit(0)
if not port_free(1456):
    raise SystemExit('port 1456 is owned by another process; refusing to start')

home = data / 'isolated-home'
home.mkdir(exist_ok=True)
default_app = root / 'package' / 'multivibe-host_0.2.138_windows_amd64' / 'app'
app = pathlib.Path(os.environ.get('MULTIVIBE_HOST_APP', default_app))
node = pathlib.Path(os.environ.get('MULTIVIBE_NODE', app.parent / 'bin' / 'node.exe'))
env = os.environ.copy()
for k in list(env):
    if k.startswith(('OAUTH_', 'OPENAI_', 'SENTRY_', 'CODEX_', 'MULTIVIBE_')):
        env.pop(k)
env.update({
    'HOST': '127.0.0.1', 'PORT': '1456', 'CONTROL_PLANE_PORT': '1456',
    'V1_EDGE_PORT': '1455', 'V1_EDGE_BASE_URL': 'http://127.0.0.1:1455',
    'V1_EDGE_INTERNAL_JOB_TOKEN': keys['internal'],
    'ADMIN_TOKEN': keys['admin'], 'PROXY_API_KEY': keys['proxy'],
    'HOST_HARNESS_HOME_DIRECTORY': str(home),
    'COMMUNITY_BENCHMARKS_ENABLED': 'false',
    'TRACE_INCLUDE_BODY': 'false', 'TRACE_INCLUDE_HEADERS': 'false',
    'MODULES_PATH': str(data / 'modules'),
    'BUNDLED_SECURITY_MODULE_PATH': str(app / 'modules/security'),
})
paths = {
    'STORE_PATH': 'accounts.json', 'OAUTH_STATE_PATH': 'oauth-state.json',
    'TRACE_FILE_PATH': 'requests.jsonl', 'TRACE_STATS_HISTORY_PATH': 'stats.jsonl',
    'CODEX_PROJECTS_PATH': 'projects.json', 'JOBS_DB_PATH': 'jobs.sqlite',
    'ANONYMOUS_USAGE_STATE_PATH': 'anonymous.json',
    'COMMUNITY_BENCHMARKS_STATE_PATH': 'community.json',
}
env.update({k: str(data / v) for k, v in paths.items()})
out = (data / 'control.stdout.log').open('a')
err = (data / 'control.stderr.log').open('a')
proc = subprocess.Popen([str(node), 'dist/server.js'], cwd=app, env=env,
                        stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
(data / 'control.pid').write_text(str(proc.pid))
for _ in range(40):
    if healthy():
        print('CONTROL_PLANE_READY 127.0.0.1:1456 pid=' + str(proc.pid))
        raise SystemExit(0)
    if proc.poll() is not None:
        raise SystemExit('control plane exited; inspect private control.stderr.log')
    time.sleep(.5)
raise SystemExit('control plane did not become ready; inspect private control.stderr.log')
