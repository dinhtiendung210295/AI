"""Fail closed for legacy writers once phased control is enabled."""
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parents[6] / 'outputs/pysb-aug-oct-prod-20261024'


def require_access(token=None, directory=None):
    token = token or os.environ.get('PYSB_PHASE_TOKEN')
    directory = Path(directory) if directory else OUT
    enabled_path = directory / 'phases/phased-control-enabled.json'
    if not enabled_path.exists():
        return
    enabled = json.loads(enabled_path.read_text(encoding='utf8'))
    active = json.loads((directory / 'phases/active-phase.json').read_text(encoding='utf8'))
    if not token or token != active.get('token') or active.get('pid') != os.getpid():
        raise RuntimeError('Only the active phased controller may write production')
    if active.get('phase') not in enabled.get('supported_phases', []) or active.get('identity') != enabled.get('identity'):
        raise RuntimeError('Phase or scope is not enabled for production writes')
