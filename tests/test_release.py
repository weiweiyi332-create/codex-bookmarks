"""Isolated installation and transport tests using fictional records only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from demo import prepare_demo

class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='codex-bookmarks-release-')
        cls.target = Path(cls.temp.name) / 'folder with spaces/codex-bookmarks'
        subprocess.run([sys.executable, str(ROOT / 'install.py'), '--dest', str(cls.target)], check=True, capture_output=True)
        cls.scripts = cls.target / 'scripts'
        cls.data = Path(cls.temp.name) / 'panel-data'
        cls.env = {**os.environ, 'CODEX_HOME': str(prepare_demo()), 'CODEX_BOOKMARKS_DATA_DIR': str(cls.data)}
        cls.server = subprocess.Popen([sys.executable, '-X', 'utf8', str(cls.scripts / 'server.py')], env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 8
        while not (cls.data / 'runtime.json').exists():
            if cls.server.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Isolated HTTP server failed to start')
            time.sleep(0.05)
        cls.runtime = json.loads((cls.data / 'runtime.json').read_text())
        cls.base = 'http://127.0.0.1:' + str(cls.runtime['port'])

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=5)
        cls.temp.cleanup()

    def request(self, path, method='GET', payload=None, auth=True, origin=None):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.runtime['token']
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.base + path, method=method, headers=headers, data=None if payload is None else json.dumps(payload).encode())
        return urllib.request.urlopen(req, timeout=3)

    def test_installed_paths_and_no_overwrite(self):
        config = json.loads((self.target / 'plugins/codex-bookmarks/.mcp.json').read_text(encoding='utf-8'))
        self.assertEqual(config['mcpServers']['bookmarks']['command'], sys.executable)
        self.assertEqual(Path(config['mcpServers']['bookmarks']['args'][-2]).resolve(), (self.scripts / 'server.py').resolve())
        result = subprocess.run([sys.executable, str(ROOT / 'install.py'), '--dest', str(self.target)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_http_fixture_read_save_and_reject(self):
        with self.request('/api/list') as r:
            items = json.load(r)['items']
        self.assertEqual(len(items), 6)
        self.assertTrue(all(x['status'] == 'ready' for x in items))
        self.assertEqual(sum(x['topic'] == '情绪建构论' for x in items), 2)
        with self.request('/api/save', 'POST', {'id': items[0]['id'], 'title': '演示测试', 'tags': ['演示'], 'note': '测试笔记', 'topic': '我的专题'}) as r:
            self.assertTrue(json.load(r)['ok'])
        self.assertTrue((self.data / 'annotations.json').exists())
        with self.request('/api/list') as r:
            changed = next(x for x in json.load(r)['items'] if x['id'] == items[0]['id'])
        self.assertEqual(changed['topic'], '我的专题')
        self.assertEqual(changed['note'], '测试笔记')
        self.assertTrue(changed['topic_manual'])
        with self.request('/api/save', 'POST', {'id': items[0]['id'], 'title': '演示测试', 'tags': ['演示'], 'note': '测试笔记', 'topic': ''}) as r:
            self.assertTrue(json.load(r)['ok'])
        with self.request('/api/list') as r:
            restored = next(x for x in json.load(r)['items'] if x['id'] == items[0]['id'])
        self.assertEqual(restored['topic'], 'EEG 基础模型')
        self.assertFalse(restored['topic_manual'])
        for headers in ({'auth': False}, {'origin': 'https://example.org'}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/list', **headers)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_launch_reuses_own_isolated_service(self):
        result = subprocess.run([sys.executable, str(self.scripts / 'launch.py')], env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), self.runtime['url'])

    def test_mcp_installed_resources_and_list(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05'}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'resources/read', 'params': {'uri': 'ui://codex-bookmarks/panel.html'}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'list_bookmarks', 'arguments': {}}},
        ]
        result = subprocess.run([sys.executable, '-X', 'utf8', str(self.scripts / 'server.py'), '--mcp'], input='\n'.join(json.dumps(x) for x in requests) + '\n', env=self.env, text=True, encoding='utf-8', capture_output=True, check=True)
        responses = [json.loads(x)['result'] for x in result.stdout.splitlines()]
        self.assertEqual(len(responses[1]['tools']), 4)
        self.assertIn('<!doctype html>', responses[2]['contents'][0]['text'])
        self.assertEqual(len(responses[3]['structuredContent']['items']), 6)

if __name__ == '__main__':
    unittest.main()
