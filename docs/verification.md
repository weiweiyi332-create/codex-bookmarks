# 发布包验证 · 2026-10-01

验证环境：Windows，Python 3.14。宣称最低 Python 3.10 基于语法/API 兼容性检查，尚未在 3.10 实机运行。没有使用真实问答验证新发布包。

## 已通过

- 原始解析测试 3 项：精确用户项匹配并过滤非最终消息、旧记录与包装格式、独立笔记写入。
- 隔离发布测试 4 项：含空格目录安装和不覆盖旧目录、HTTP 虚构记录读取/笔记写入/未授权与外站 Origin 拒绝、启动器复用隔离服务、MCP 初始化/工具/UI 资源/收藏列表。
- skill-creator 的 quick_validate.py 格式检查。
- 安装后的 MCP 配置指向安装目录和实际 Python 路径，源包不包含开发者的固定路径配置。
- 发布文件使用显式清单打包；不含 data、runtime.json、日志、数据库、session JSONL、个人笔记或原始真实截图。

运行：

```powershell
python -m unittest discover -s skills/codex-bookmarks/scripts -p "test_*.py" -v
python -m unittest discover -s tests -v
```

## 未完成的兼容性验证

- 新发布包在其他用户实际 Codex 数据、不同客户端版本上的读取。
- 新安装插件在原生侧栏入口的显示与固定。
- macOS/Linux、Python 3.10 实机运行。
- 新发布包的浏览器视觉回归；原工具验收不能替代新安装包的浏览器实测。
- 精确跳转到某一条回答。

## 测试中修正

隔离安装测试最初将 Windows 短路径与展开后的长路径进行文本比较，产生一次失败；改为比较解析后的路径，重新运行 4 项测试通过。第一次选择的 Python 运行时缺少 PyYAML，格式校验未执行成功；改用已具备依赖的系统 Python 后通过。
