"""Start or reuse the local panel. Printing its URL lets Codex open the right panel."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CODEX_BOOKMARKS_DATA_DIR') or ROOT.parent / 'data').expanduser()
DATA.mkdir(parents=True, exist_ok=True)

def existing():
    try:
        d = json.loads((DATA / 'runtime.json').read_text(encoding='utf-8'))
        req = urllib.request.Request(f"http://127.0.0.1:{int(d['port'])}/api/health", headers={'Authorization': 'Bearer ' + d['token']})
        with urllib.request.urlopen(req, timeout=1) as r:
            if json.load(r).get('app') == 'codex-bookmarks':
                return d['url']
    except Exception:
        return None

url = existing()
if not url:
    with (DATA / 'server.log').open('ab') as log:
        subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'server.py')], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == 'nt' else 0,
                         close_fds=True)
    for _ in range(40):
        time.sleep(.1)
        url = existing()
        if url:
            break
if not url:
    raise SystemExit('收藏夹启动失败，请查看 data/server.log')
print(url)
if '--browser' in sys.argv:
    import webbrowser
    webbrowser.open(url)
