"""交接资料格式和原文完整性测试。"""
from pathlib import Path
import json
import subprocess
import sys
import unittest

from corpus import read_collection

ROOT = Path(__file__).resolve().parents[1]


def records(name):
    return read_collection(ROOT / "data" / (name + ".json"))


class MaterialTests(unittest.TestCase):
    def test_collections_are_utf8_record_arrays(self):
        for name, fields in FIELDS.items():
            with self.subTest(collection=name):
                rows = records(name)
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(set(row), set(fields))
                    self.assertIsInstance(row["id"], str)
                    self.assertTrue(row["id"])

    def test_reader_retains_exact_text_and_order(self):
        result = subprocess.check_output(
            [sys.executable, "-m", "corpus", PRIMARY, "--id", LINE_ID],
            cwd=ROOT, text=True, encoding="utf-8",
        )
        original = [row for row in records(PRIMARY) if row["id"] == LINE_ID]
        self.assertTrue(original)
        self.assertEqual(json.loads(result), original)

    def test_answer_revisions_keep_prior_sources_and_teacher_records(self):
        briefs = {row["id"] for row in records("briefs")}
        answers = {row["id"]: row for row in records("answers")}
        pupils = {row["id"] for row in records("students")}
        for row in answers.values():
            self.assertIn(row["学生"], pupils)
            if row["引自"]:
                self.assertIn(row["引自"], briefs | set(answers))
        for row in records("marking"):
            for key in row["对象"].split("/"):
                self.assertEqual(answers[key]["学生"], row["学生"])
        self.assertEqual(answers["A2"]["引自"], answers["A3"]["引自"])
        self.assertLess(answers["A2"]["序次"], answers["A3"]["序次"])


PRIMARY = 'answers'
LINE_ID = 'A2'
FIELDS = {
    "briefs": [
        "id",
        "阶段",
        "版本",
        "原文"
    ],
    "answers": [
        "id",
        "学生",
        "分段",
        "序次",
        "日期",
        "引自",
        "文字"
    ],
    "rubrics": [
        "id",
        "要求",
        "版次",
        "层级",
        "原文"
    ],
    "marking": [
        "id",
        "学生",
        "教师",
        "对象",
        "规准",
        "时间",
        "动作",
        "原文"
    ],
    "students": [
        "id",
        "方向",
        "阶段"
    ]
}
