import json
from pathlib import Path
import tempfile
import unittest
from bookmarks import Library, parse_turn, organize, suggest_topic

class ParsingTests(unittest.TestCase):
    def test_topic_uses_question_only(self):
        self.assertEqual(suggest_topic('情绪建构论如何理解个体差异？'), '情绪建构论')
        self.assertEqual(suggest_topic('Barrett 的情绪理论是什么？'), '情绪建构论')
        self.assertEqual(suggest_topic('这句话是什么意思？'), '其他主题')
        self.assertEqual(suggest_topic('NeuroLM 如何训练？'), 'EEG 基础模型')
        self.assertEqual(suggest_topic('买什么床单？'), '其他主题')

    def test_empty_topic_catalog_and_topic_only_update(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Library(codex_home=Path(d)/'no-codex', data_dir=Path(d)/'notes')
            self.assertEqual(lib.create_topic('  自己的专题  '), '自己的专题')
            lib.create_topic('自己的专题')
            self.assertEqual(lib.topic_catalog()['topics'], ['自己的专题'])
            key = 'c' * 24
            lib.save(key, '原始标题', ['保留标签'], '保留笔记')
            lib.set_topic(key, '第二个专题')
            entry = lib._metadata()[key]
            self.assertEqual((entry['title'], entry['tags'], entry['note']), ('原始标题', ['保留标签'], '保留笔记'))
            self.assertEqual(entry['topic'], '第二个专题')
            self.assertTrue(entry['topic_reviewed'])
            self.assertIn('第二个专题', lib.topic_catalog()['topics'])
            lib.set_topic(key, '')
            self.assertNotIn('topic', lib._metadata()[key])
            self.assertTrue(lib._metadata()[key]['topic_reviewed'])
            for value in (' ', 5, '长'*81):
                with self.assertRaises(ValueError): lib.create_topic(value)

    def test_manual_topic_survives_legacy_save_and_can_reset(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Library(codex_home=Path(d)/'no-codex', data_dir=Path(d)/'notes')
            key = 'b' * 24
            lib.save(key, '标题', ['标签'], '原有笔记', '  情绪构建论  ')
            self.assertEqual(lib._metadata()[key]['topic'], '情绪建构论')
            lib.save(key, '新标题', ['标签'], '原有笔记')
            self.assertEqual(lib._metadata()[key]['topic'], '情绪建构论')
            self.assertEqual(lib._metadata()[key]['note'], '原有笔记')
            lib.save(key, '新标题', ['标签'], '原有笔记', '')
            self.assertNotIn('topic', lib._metadata()[key])
            for invalid in (['topic'], 3, '长' * 81):
                with self.assertRaises(ValueError):
                    lib.save(key, '标题', [], '笔记', invalid)

    def test_exact_user_and_final_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'history.jsonl'
            rows = [
                {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 't1'}},
                {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': 't1', 'item': {'type': 'UserMessage', 'id': 'u1', 'content': [{'text': '第一问'}]}}},
                {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': 't1', 'item': {'type': 'AgentMessage', 'phase': 'commentary', 'content': [{'text': '不应显示的进度'}]}}},
                {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': 't1', 'item': {'type': 'UserMessage', 'id': 'u2', 'content': [{'text': '补充条件'}]}}},
                {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': 't1', 'item': {'type': 'AgentMessage', 'phase': 'final', 'content': [{'text': '完整答案'}]}}},
                {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': 't2', 'item': {'type': 'AgentMessage', 'phase': 'final', 'content': [{'text': '不相关答案'}]}}},
                {'type': 'compacted', 'payload': {'replacement_history': [{'role': 'assistant', 'text': '不应作为收藏的压缩总结'}]}},
            ]
            path.write_text('\n'.join(json.dumps(x) for x in rows) + '\n{"partial":', encoding='utf-8')
            found = parse_turn(path, 't1', 'u2')
            self.assertEqual(found['question'], '补充条件')
            self.assertEqual(found['answer'], '完整答案')
            self.assertEqual(found['additional_prompts'], ['第一问'])
            self.assertIsNone(parse_turn(path, 't1', 'bad'))

    def test_legacy_and_wrapper(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'old.jsonl'
            rows = [{'type': 'turn_context', 'payload': {'turn_id': 'old'}},
                    {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'text': '## My request:\nLaBraM EEG 模型'}]}},
                    {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'analysis', 'content': [{'text': 'private reasoning'}]}},
                    {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'final', 'content': [{'text': '答案'}]}}]
            path.write_text('\n'.join(json.dumps(x) for x in rows), encoding='utf-8')
            found = parse_turn(path, 'old')
            self.assertEqual(found['answer'], '答案')
            title, tags = organize(found['question'], found['answer'])
            self.assertEqual(title, 'LaBraM EEG 模型')
            self.assertIn('LaBraM', tags)

    def test_annotations_are_independent(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Library(codex_home=Path(d)/'no-codex', data_dir=Path(d)/'notes')
            lib.save('a'*24, '测试标题', ['情绪', '情绪'], '笔记')
            self.assertEqual(lib._metadata()['a'*24]['tags'], ['情绪'])
            self.assertFalse((Path(d)/'no-codex').exists())
            with self.assertRaises(ValueError):
                lib.save('../bad', '', [], '')

if __name__ == '__main__':
    unittest.main()
