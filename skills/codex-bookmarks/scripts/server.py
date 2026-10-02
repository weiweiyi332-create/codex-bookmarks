from __future__ import annotations
import argparse
import base64
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from bookmarks import Library

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CODEX_BOOKMARKS_DATA_DIR') or ROOT.parent / 'data').expanduser()
APP = Library(data_dir=DATA)
TOKEN = secrets.token_urlsafe(32)
UI_URI = 'ui://codex-bookmarks/panel.html'
ICON_PATH = ROOT.parent / 'plugins/codex-bookmarks/assets/icon.png'
ICONS = [{'src': 'data:image/png;base64,' + base64.b64encode(ICON_PATH.read_bytes()).decode(), 'mimeType': 'image/png', 'sizes': ['128x128']}]

def execute(name, args):
    if name in ('open_bookmarks', 'list_bookmarks'):
        return APP.list()
    if name == 'save_annotation':
        item = APP.item(args.get('id'))
        if item is None:
            raise ValueError('此收藏已被取消，请刷新列表')
        APP.save(args['id'], args.get('title', item['title']), args.get('tags', item['tags']), args.get('note', item['note']), args.get('topic'))
        return {'ok': True}
    if name == 'create_topic':
        return {'ok': True, 'topic': APP.create_topic(args.get('topic'))}
    if name == 'set_bookmark_topic':
        if APP.item(args.get('id')) is None:
            raise ValueError('此收藏已被取消，请刷新列表')
        APP.set_topic(args['id'], args.get('topic', ''))
        return {'ok': True}
    if name == 'initialize_topic_review':
        APP.initialize_topic_review()
        return {'ok': True}
    if name == 'open_source':
        item = APP.item(args.get('id'))
        if not item:
            raise ValueError('收藏不存在')
        os.startfile(item['url'])
        return {'ok': True, 'mode': 'conversation'}
    raise ValueError('未知操作')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, payload, mime='application/json; charset=utf-8'):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        host = self.headers.get('Host', '')
        if host != f'127.0.0.1:{self.server.server_port}':
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            return False
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        return bool(token) and hmac.compare_digest(token, TOKEN)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == '/' and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}':
            return self.send(200, (ROOT / 'panel.html').read_bytes(), 'text/html; charset=utf-8')
        if not self.authorized():
            return self.send(403, {'error': '请通过收藏夹启动入口打开'})
        try:
            if route == '/api/list':
                return self.send(200, APP.list())
            if route == '/api/health':
                return self.send(200, {'app': 'codex-bookmarks', 'ok': True})
            self.send(404, {'error': '不存在'})
        except Exception as exc:
            self.send(500, {'error': '读取失败：' + str(exc)})

    def do_POST(self):
        if not self.authorized():
            return self.send(403, {'error': '请求未授权'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if n < 0 or n > 100000:
                return self.send(413, {'error': '内容过长'})
            args = json.loads(self.rfile.read(n))
            names = {'/api/save': 'save_annotation', '/api/open': 'open_source', '/api/create-topic': 'create_topic', '/api/set-topic': 'set_bookmark_topic', '/api/init-topics': 'initialize_topic_review'}
            name = names.get(urlsplit(self.path).path)
            if not name:
                return self.send(404, {'error': '不存在'})
            self.send(200, execute(name, args))
        except (ValueError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except Exception as exc:
            self.send(500, {'error': '操作失败：' + str(exc)})

def mcp():
    """Small JSON-lines MCP transport; no network or third-party dependencies."""
    schemas = {
        'open_bookmarks': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'list_bookmarks': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'save_annotation': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'title': {'type': 'string'}, 'tags': {'type': 'array', 'items': {'type': 'string'}}, 'note': {'type': 'string'}, 'topic': {'type': 'string', 'maxLength': 80, 'description': '自定义主题；空文字恢复自动归类，省略则保留原主题'}}, 'required': ['id']},
        'open_source': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']},
        'create_topic': {'type': 'object', 'properties': {'topic': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['topic']},
        'set_bookmark_topic': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'topic': {'type': 'string', 'maxLength': 80}}, 'required': ['id', 'topic']},
        'initialize_topic_review': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    }
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if 'id' not in req:
                continue
            method, p = req.get('method'), req.get('params', {})
            if method == 'initialize':
                result = {'protocolVersion': p.get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}, 'resources': {}}, 'serverInfo': {'name': 'codex-bookmarks', 'version': '0.3.0'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                ts = []
                for name, schema in schemas.items():
                    ui = {'visibility': ['app', 'model']}
                    meta = {'ui': ui}
                    if name == 'open_bookmarks':
                        ui['resourceUri'] = UI_URI
                        meta['openai/ui'] = {'entrypoints': [{'type': 'thread'}, {'type': 'global'}]}
                    ts.append({'icons': ICONS, 'name': name, 'title': {'open_bookmarks': '收藏夹', 'list_bookmarks': '刷新收藏', 'save_annotation': '整理收藏', 'open_source': '打开原对话', 'create_topic': '新建主题', 'set_bookmark_topic': '更改主题', 'initialize_topic_review': '初始化新收藏归类'}[name], 'description': '管理本机 Codex 原生问答收藏；来源跳转目前打开整个对话。', 'inputSchema': schema, '_meta': meta, 'annotations': {'readOnlyHint': name in ('open_bookmarks', 'list_bookmarks'), 'destructiveHint': False, 'openWorldHint': False}})
                result = {'tools': ts}
            elif method == 'resources/list':
                result = {'resources': [{'uri': UI_URI, 'name': '收藏夹', 'mimeType': 'text/html;profile=mcp-app'}]}
            elif method == 'resources/read' and p.get('uri') == UI_URI:
                result = {'contents': [{'uri': UI_URI, 'mimeType': 'text/html;profile=mcp-app', 'text': (ROOT / 'panel.html').read_text(encoding='utf-8'), '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': []}}}}]}
            elif method == 'tools/call':
                try:
                    obj = execute(p['name'], p.get('arguments', {}))
                    result = {'content': [{'type': 'text', 'text': ('已读取 ' + str(len(obj['items'])) + ' 条收藏。') if 'items' in obj else '操作完成。'}], 'structuredContent': obj}
                    if p['name'] == 'open_bookmarks':
                        result['_meta'] = {'ui': {'resourceUri': UI_URI}}
                except Exception as exc:
                    result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
            else:
                print(json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'error': {'code': -32601, 'message': 'Method not found'}}), flush=True)
                continue
            print(json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'result': result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(str(exc), file=sys.stderr, flush=True)

if __name__ == '__main__':
    if '--mcp' in sys.argv:
        mcp()
    else:
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        DATA.mkdir(parents=True, exist_ok=True)
        info = {'port': server.server_port, 'token': TOKEN, 'pid': os.getpid(), 'url': f'http://127.0.0.1:{server.server_port}/#token={TOKEN}'}
        (DATA / 'runtime.json').write_text(json.dumps(info), encoding='utf-8')
        server.serve_forever()
