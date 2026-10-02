"""Create fictional local fixtures and start a separate demonstration panel."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def prepare_demo():
    home = ROOT / 'data/demo-codex-home'
    home.mkdir(parents=True, exist_ok=True)
    records = [
        ('如何把读书笔记整理成可检索的知识库？', '**先保留原始问题，再写自己的理解。**\n\n- 用主题标签归类。\n- 添加一句为什么收藏。\n- 每周回看最有价值的内容。'),
        ('帮我制定一个适合新手的 Python 学习计划', '**先做一个能运行的小项目。**\n\n第一周学习变量和函数，第二周读取文件，第三周制作个人待办工具。'),
        ('如何为周末旅行准备行李？', '**按场景列清单。**\n\n| 场景 | 物品 |\n|---|---|\n| 出行 | 证件、充电器 |\n| 日常 | 换洗衣物、水杯 |'),
        ('情绪建构论强调的个体差异是什么意思？', '这是一条用于界面演示的虚构问答。\n\n**同主题的问题会集中展示。** 可以给回答加上自己的笔记。'),
        ('Barrett 的情绪理论怎样理解情境？', '这是一条用于界面演示的虚构问答。\n\n可以在同一个主题里按时间阅读，也可以按标题寻找。'),
        ('LaBraM 和 NeuroLM 有什么区别？', '这是一条用于界面演示的虚构问答。\n\n这类问题归入 **EEG 基础模型**，可在整理面板修改主题。'),
    ]
    groups = {}
    with sqlite3.connect(home / 'state_1.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, name TEXT, title TEXT, rollout_path TEXT)')
        for i, (question, answer) in enumerate(records, 1):
            thread, turn, user = f'demo-thread-{i}', f'demo-turn-{i}', f'demo-user-{i}'
            path = home / f'demo-{i}.jsonl'
            rows = [
                {'timestamp': f'2026-09-{20+i:02}T10:00:00Z', 'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': turn, 'item': {'type': 'UserMessage', 'id': user, 'content': [{'text': question}]}}},
                {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': turn, 'item': {'type': 'AgentMessage', 'phase': 'final', 'content': [{'text': answer}]}}},
            ]
            path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
            db.execute('INSERT OR REPLACE INTO threads VALUES (?, ?, ?, ?)', (thread, '演示数据 · ' + question, question, str(path)))
            groups[thread] = [{'turnId': turn + ':' + user}]
    state = {'electron-persisted-atom-state': {'pinned-conversation-turns-v1': {'demo-account': groups}}}
    (home / '.codex-global-state.json').write_text(json.dumps(state), encoding='utf-8')
    return home

def main():
    parser = argparse.ArgumentParser(description='使用虚构问答打开演示收藏夹，不读取真实 Codex 数据')
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    home = prepare_demo()
    scripts = ROOT / 'skills/codex-bookmarks/scripts'
    env = {**os.environ, 'CODEX_HOME': str(home), 'CODEX_BOOKMARKS_DATA_DIR': str(ROOT / 'data/demo-panel')}
    command = [sys.executable, '-X', 'utf8', str(scripts / 'launch.py')]
    if args.browser:
        command.append('--browser')
    print('演示模式：所有问答均为虚构；打开原对话不对应真实对话。', flush=True)
    subprocess.run(command, env=env, check=True)

if __name__ == '__main__':
    main()
