"""Install the self-contained skill without changing Codex preferences."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

def main():
    parser = argparse.ArgumentParser(description='安装 Codex 收藏夹 skill（Python 3.10+）')
    parser.add_argument('--dest', type=Path, help='自定义技能安装目录，目录名建议 codex-bookmarks')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('需要 Python 3.10 或更高版本')
    home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
    target = (args.dest or home / 'skills/codex-bookmarks').expanduser().resolve()
    source = Path(__file__).resolve().parent / 'skills/codex-bookmarks'
    if target.exists():
        parser.error(f'目标目录已存在，未覆盖：{target}。请备份旧版本后手动处理，或指定 --dest。')
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('data', '__pycache__', '*.pyc', '.mcp.json'))
    config = {'mcpServers': {'bookmarks': {'command': sys.executable, 'args': ['-X', 'utf8', str(target / 'scripts/server.py'), '--mcp']}}}
    plugin = target / 'plugins/codex-bookmarks'
    (plugin / '.mcp.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'已安装 skill：{target}')
    print('在 Codex 下一轮对话输入：$codex-bookmarks 打开收藏夹')
    print(f'备用启动：python "{target / "scripts/launch.py"}" --browser')
    print('本安装器没有注册或启用插件，也没有修改 Codex 配置。')
    print(f'可选插件目录（须客户端支持）：{plugin}')

if __name__ == '__main__':
    main()
