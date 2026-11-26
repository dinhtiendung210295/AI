"""Explicit per-user native host registration. Does not change PowerShell policy."""
import argparse
import json
from pathlib import Path
import re
import sys
import winreg

KEY = r"Software\Google\Chrome\NativeMessagingHosts\local.chatgpt_dictation"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extension-id')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if not args.remove and (not args.extension_id or not re.fullmatch('[a-p]{32}', args.extension_id)):
        parser.error('Supply --extension-id with the ID shown at chrome://extensions')
    root = Path(__file__).resolve().parent
    manifest = root / 'native-host.json'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            existing = winreg.QueryValueEx(key, '')[0]
        if str(existing).casefold() != str(manifest).casefold():
            raise RuntimeError('Existing registration belongs to another path; left unchanged.')
    except FileNotFoundError:
        pass
    if args.remove:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
        except FileNotFoundError:
            pass
        print('Removed per-user registration. Files and Chrome profile kept.')
        return
    python = root / '.venv/Scripts/python.exe'
    if not python.is_file():
        raise RuntimeError('Dedicated Python environment not found.')
    launcher = root / 'native-host.cmd'
    launcher.write_text(f'@echo off\n"{python}" -u "{root / "native_host.py"}"\n', encoding='ascii')
    manifest.write_text(json.dumps({
        'name': 'local.chatgpt_dictation',
        'description': 'Local dictation clipboard and guarded paste',
        'path': str(launcher),
        'type': 'stdio',
        'allowed_origins': [f'chrome-extension://{args.extension_id}/'],
    }, indent=2), encoding='utf-8')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest))
    print('Registered for this Windows user only.')
    print('Extension ID:', args.extension_id)
    print('No admin, PowerShell policy changes, startup task or network listener.')
    print('Next: reload extension, open it on ChatGPT, enable Windows bridge.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Registration failed:', exc, file=sys.stderr)
        raise SystemExit(1)
