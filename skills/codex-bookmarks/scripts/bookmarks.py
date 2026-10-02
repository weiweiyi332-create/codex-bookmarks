"""Read native Codex bookmarks without changing any Codex-owned files."""
from __future__ import annotations
import hashlib
import os
from contextlib import closing
import html
import json
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

RULES = {
    '情绪与心理': ['情绪', '情感', 'emotion', 'barrett', '建构论', '心理'],
    '脑电与神经科学': ['eeg', '脑电', '神经', 'seed', 'neurolm', 'labram'],
    '模型与方法': ['模型', '训练', '架构', '算法', 'transformer', 'learning', '分类'],
    '研究设计': ['研究', '实验', '假设', '创新', '跨被试', '基线', '消融'],
    '文献阅读': ['论文', '文献', 'doi', '文章', '速读', 'paper'],
    '工具与软件': ['codex', '插件', '软件', '安装', '收藏', '代码', '配置'],
}

# Specific topics precede broad categories. Question matches take precedence
# over answer matches so an incidental comparison does not move a bookmark.
TOPICS = {
    '情绪建构论': ['情绪建构论', '情绪构建论', '建构情绪', '建构论', '构建论', 'constructed emotion', 'constructionist', 'barrett', '巴雷特'],
    'EEG 基础模型': ['labram', 'neurolm', '脑电基础模型', 'eeg foundation', 'eeg大模型', '脑电大模型'],
    '跨被试情绪识别': ['跨被试', 'cross-subject', 'cross subject', '被试适应', '被试泛化'],
    'EEG 情绪识别': ['脑电情绪', '脑电情感', 'eeg emotion', 'eeg情绪', 'eeg情感', 'seed'],
    'GitHub 与开源': ['github', '开源', 'gitlab'],
    'Codex 使用与工具': ['codex', '收藏夹', 'skill', '插件'],
    'Python 学习': ['python', 'python学习'],
    '知识管理与笔记': ['知识库', '读书笔记', '知识管理', '笔记整理'],
    '旅行规划': ['旅行', '旅游', '行李', '出游'],
}

def normalize_topic(value):
    value = ' '.join(unicodedata.normalize('NFKC', value).split())
    for topic, aliases in TOPICS.items():
        if value.casefold() in {topic.casefold(), *(alias.casefold() for alias in aliases)}:
            return topic
    return value

def suggest_topic(question, answer, title=''):
    for text in (readable_question(question) + '\n' + title, answer):
        text = text.casefold()
        for topic, words in TOPICS.items():
            if any(re.search(r'(?<![a-z])' + re.escape(w) + r'(?![a-z])', text) if w.isascii() else w in text for w in words):
                return topic
    _, tags = organize(question, answer)
    return tags[0] if tags[0] != '未分类' else '其他主题'

def text_of(content):
    if isinstance(content, str):
        return content
    return '\n'.join(x.get('text', '') for x in (content or []) if isinstance(x, dict) and isinstance(x.get('text'), str))

def readable_question(text):
    # Wrapper removal is for display only. The exact source remains available.
    if '## My request:' in text:
        text = text.rsplit('## My request:', 1)[1]
    text = re.sub(r'<response-annotations>.*?</response-annotations>', '', text, flags=re.S)
    return html.unescape(text).strip()

def organize(question, answer):
    q = readable_question(question)
    clean = re.sub(r'[*#>`]+', '', q)
    clean = re.sub(r'\s+', ' ', clean).strip()
    tags = [name for name, words in RULES.items() if any(w in (q + '\n' + answer[:5000]).lower() for w in words)]
    for label in ['LaBraM', 'NeuroLM', 'MAT', 'mMLDA', 'SEED', 'EEG', 'LLM']:
        if re.search(r'(?<![a-z])' + re.escape(label) + r'(?![a-z])', q + '\n' + answer[:5000], re.I):
            tags.append(label)
    return clean[:72] + ('…' if len(clean) > 72 else ''), tags or ['未分类']

def parse_turn(path, turn_id, user_id=None):
    """Use completed UI items; never index reasoning, tool output or compacted context."""
    users, finals, fallback_users, fallback_finals = [], [], [], []
    current = None
    date = ''
    try:
        stream = Path(path).open(encoding='utf-8')
    except OSError:
        return None
    with stream:
        for line in stream:
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            p = record.get('payload', {})
            if not isinstance(p, dict):
                continue
            typ = record.get('type')
            if typ == 'turn_context':
                current = p.get('turn_id')
            elif typ == 'event_msg' and p.get('type') == 'task_started':
                current = p.get('turn_id')
            if typ == 'event_msg' and p.get('type') == 'item_completed' and p.get('turn_id') == turn_id:
                item = p.get('item', {})
                itype = item.get('type', '').lower()
                if itype == 'usermessage':
                    users.append((item.get('id'), text_of(item.get('content'))))
                    date = date or record.get('timestamp', '')
                elif itype == 'agentmessage' and item.get('phase') in ('final', 'final_answer'):
                    finals.append(text_of(item.get('content')))
            if typ == 'response_item' and p.get('type') == 'message':
                msg_turn = p.get('internal_chat_message_metadata_passthrough', {}).get('turn_id') or current
                if msg_turn != turn_id:
                    continue
                if p.get('role') == 'user':
                    fallback_users.append((p.get('id'), text_of(p.get('content'))))
                    date = date or record.get('timestamp', '')
                elif p.get('role') == 'assistant' and p.get('channel') == 'final':
                    fallback_finals.append(text_of(p.get('content')))
    us = users or fallback_users
    if not us:
        return None
    exact = next((text for uid, text in us if uid == user_id), None)
    if user_id and users and exact is None:
        return None
    question = exact if exact is not None else us[0][1]
    answer = '\n\n'.join(dict.fromkeys(finals or fallback_finals))
    return {'question': question, 'answer': answer, 'date': date,
            'additional_prompts': [text for uid, text in us if text != question],
            'status': 'ready' if answer else 'pending'}

class Library:
    def __init__(self, codex_home=None, data_dir=None):
        self.home = Path(codex_home or os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
        self.data = Path(data_dir or Path(__file__).parent / 'data')
        self.data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.cache = {}
        self.meta_path = self.data / 'annotations.json'

    def _metadata(self):
        try:
            return json.loads(self.meta_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}

    def save(self, key, title, tags, note, topic=None):
        if not re.fullmatch(r'[0-9a-f]{24}', key):
            raise ValueError('收藏标识无效')
        if not isinstance(tags, list) or any(not isinstance(x, str) for x in tags):
            raise ValueError('标签格式无效')
        if not isinstance(title, str) or not isinstance(note, str):
            raise ValueError('标题和笔记必须是文字')
        if len(title) > 200 or len(note) > 20000 or len(tags) > 30:
            raise ValueError('内容过长')
        if topic is not None and (not isinstance(topic, str) or len(topic) > 80):
            raise ValueError('主题必须是 80 字以内的文字')
        with self.lock:
            meta = self._metadata()
            meta[key] = {**meta.get(key, {}), 'title': title.strip(), 'tags': list(dict.fromkeys(x.strip()[:60] for x in tags if x.strip())), 'note': note}
            if topic is not None:
                topic = normalize_topic(topic)
                if topic:
                    meta[key]['topic'] = topic
                else:
                    meta[key].pop('topic', None)
            tmp = self.meta_path.with_suffix('.tmp')
            tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(self.meta_path)

    def _db(self):
        paths = list(self.home.glob('state_*.sqlite'))
        if not paths:
            raise FileNotFoundError('找不到本机 Codex 对话索引')
        db = max(paths, key=lambda p: int(re.search(r'state_(\d+)', p.name)[1]))
        conn = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        return conn

    def _resolve(self, row, turn_id, user_id):
        path = Path(row['rollout_path'])
        paths = [path]
        # Paginated histories can leave older turns in earlier files.
        for root in ('sessions', 'archived_sessions'):
            folder = self.home / root
            if folder.exists():
                paths.extend(x for x in folder.rglob('*' + row['id'] + '*.jsonl') if x != path)
        for candidate in dict.fromkeys(paths):
            try:
                stamp = (candidate.stat().st_mtime_ns, candidate.stat().st_size)
            except OSError:
                continue
            ck = (str(candidate), turn_id, user_id, stamp)
            if ck not in self.cache:
                self.cache[ck] = parse_turn(candidate, turn_id, user_id)
            found = self.cache[ck]
            if found:
                return found
        return None

    def list(self):
        with self.lock:
            state = json.loads((self.home / '.codex-global-state.json').read_text(encoding='utf-8'))
            groups = state.get('electron-persisted-atom-state', {}).get('pinned-conversation-turns-v1', {})
            meta = self._metadata()
            items, warnings = [], []
            with closing(self._db()) as conn:
                for account, threads in groups.items():
                    for thread_id, bookmarks in threads.items():
                        row = conn.execute('SELECT * FROM threads WHERE id=?', (thread_id,)).fetchone()
                        for bookmark in bookmarks:
                            raw = bookmark.get('turnId', '')
                            turn_id, _, user_id = raw.partition(':')
                            if user_id.startswith('transcript:'):
                                user_id = ''
                            key = hashlib.sha256(f'{account}/{thread_id}/{raw}'.encode()).hexdigest()[:24]
                            found = self._resolve(row, turn_id, user_id or None) if row else None
                            if not found:
                                found = {'question': '', 'answer': '', 'date': '', 'additional_prompts': [], 'status': 'unavailable'}
                            title, auto_tags = organize(found['question'], found['answer'])
                            custom = meta.get(key, {})
                            auto_topic = suggest_topic(found['question'], found['answer'], custom.get('title', ''))
                            thread_title = (row['name'] or row['title']) if row else '未找到本机对话'
                            thread_title = readable_question(thread_title).replace('\n', ' ')[:100]
                            items.append({**found, 'id': key, 'thread_id': thread_id, 'turn_id': turn_id,
                                          'title': custom.get('title') or title or '暂时无法读取的收藏',
                                          'tags': custom.get('tags', auto_tags), 'auto_tags': auto_tags,
                                          'topic': custom.get('topic') or auto_topic, 'auto_topic': auto_topic,
                                          'topic_manual': bool(custom.get('topic')),
                                          'note': custom.get('note', ''), 'thread_title': thread_title,
                                          'url': 'codex://threads/' + thread_id,
                                          'display_question': readable_question(found['question'])})
            items.sort(key=lambda x: x['date'], reverse=True)
            return {'items': items, 'synced_at': time.time(), 'warnings': warnings,
                    'source': '本机 Codex 原生书签', 'jump_mode': 'conversation',
                    'classification': '本地关键词自动归类'}

    def item(self, key):
        return next((x for x in self.list()['items'] if x['id'] == key), None)
