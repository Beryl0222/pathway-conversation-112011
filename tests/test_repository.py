"""资料只读、来源链与图表转写的测试。"""
import unittest

from assessment.repository import Repository
from assessment.fragments import (
    CALC,
    COPY,
    GROUP,
    OBSERVATION,
    TRANSCRIBE,
    classify_answer,
    split_sentences,
)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def test_loading_keeps_original_records_unchanged(self):
        # 派生仓储不改写原始资料字段。
        self.assertEqual(self.repo.answers["A1"]["文字"][:7], "我们记录了八点")
        self.assertEqual(self.repo.briefs["B3"]["版本"], "1")

    def test_provenance_chain_follows_answer_and_brief_links(self):
        self.assertEqual(self.repo.provenance_chain("A2"), ["A2", "A1", "B3"])
        self.assertEqual(self.repo.source_briefs("A8"), ["B3"])
        # A6 直接引用经核准修订的观测表 B4。
        self.assertEqual(self.repo.source_briefs("A6"), ["B4"])
        self.assertEqual(self.repo.revised_from("B4"), "B3")

    def test_table_values_extracted_from_both_wordings(self):
        # B3 是“3 个达标点、8 个记录点”，B4 是“达标点修订为 2 个、记录点仍 8 个”。
        self.assertEqual((self.repo.tables["B3"].qualified,
                          self.repo.tables["B3"].total,
                          self.repo.tables["B3"].ratio), (3, 8, 3 / 8))
        self.assertEqual((self.repo.tables["B4"].qualified,
                          self.repo.tables["B4"].total,
                          self.repo.tables["B4"].ratio), (2, 8, 2 / 8))

    def test_answers_are_ordered_by_segment_and_sequence(self):
        ids = [row["id"] for row in self.repo.answers_of("S1")]
        self.assertEqual(ids, ["A1", "A2", "A3"])

    def test_marking_objects_expand_slash_notation(self):
        m5 = next(m for m in self.repo.marking if m["id"] == "M5")
        self.assertEqual(self.repo.objects_of(m5), ["A1", "A2"])


class FragmentTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def kinds(self, answer_id):
        return [(f.kind, f.needs_review) for f in
                classify_answer(self.repo.answers[answer_id], self.repo)]

    def test_guidebook_paraphrase_is_copy_not_own_calculation(self):
        # S2 引用指导书 B2 的句子必须记为抄题转述且待审，不能当成自己的计算表现。
        kinds = self.kinds("A4")
        self.assertEqual(kinds[0][0], COPY)
        self.assertTrue(kinds[0][1])

    def test_point_statement_backed_by_observation_table_is_transcription(self):
        kinds = dict((k, r) for k, r in self.kinds("A1"))
        self.assertIn(TRANSCRIBE, kinds)
        self.assertIn(CALC, kinds)

    def test_group_only_record_is_distinguished_from_personal_practice(self):
        # A7 附组表且声明“我没有做采样”：小组记录与个人分工同句，转教师核。
        labels = [f for f in classify_answer(self.repo.answers["A7"], self.repo)]
        group = next(f for f in labels if f.kind == GROUP)
        self.assertTrue(group.needs_review)
        self.assertIn("个人", group.review_reason)
        # A5“其余由记录员补”只有小组信号，不标待审但也不产生个人实践支撑。
        a5 = classify_answer(self.repo.answers["A5"], self.repo)
        self.assertTrue(any(f.kind == GROUP and not f.needs_review for f in a5))

    def test_intent_sentence_is_not_counted_as_implemented_observation(self):
        labels = classify_answer(self.repo.answers["A2"], self.repo)
        # “明天在东端复测”所在句仍含已实施的遮挡动作，按已实施观察并待审归属；
        # 但纯意图措辞不会被单独放行为实践证据（见 evidence 测试）。
        self.assertTrue(any(f.kind == OBSERVATION for f in labels))

    def test_sentence_splitting_preserves_text(self):
        joined = "".join(split_sentences(self.repo.answers["A1"]["文字"]))
        self.assertEqual(joined, self.repo.answers["A1"]["文字"])


if __name__ == "__main__":
    unittest.main()
