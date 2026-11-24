"""补交处理、反馈结构与阶段汇入门槛的测试。"""
import unittest

from assessment.repository import Repository
from assessment.resubmission import review_resubmissions
from assessment.feedback import build_feedback
from assessment.stage import build_stage_record, comparison_view
from assessment.judgments import SIGNED


class ResubmissionTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.reviews = {r.answer_id: r for r in review_resubmissions(self.repo)}

    def test_unchanged_input_freezes_prior_decisions_without_double_counting(self):
        # S1 的 A3：来源仍是 A1->B3，输入未变，前段签定保留。
        review = self.reviews["A3"]
        self.assertTrue(review.input_unchanged)
        # 只冻结真正指向 A2 的前段批语（M2/M3/M4），跨段回执 M5 不冒充。
        self.assertEqual(set(review.prior_decisions_frozen), {"M2", "M3", "M4"})
        self.assertIn("不重复计数值错误", review.treatment)
        self.assertFalse(review.needs_teacher)

    def test_revised_observation_is_decided_by_later_material_and_rubric(self):
        # S2 的 A6 换用核准修订表 B4：不自动改判，按后项材料与 R2 新版重评。
        review = self.reviews["A6"]
        self.assertFalse(review.input_unchanged)
        self.assertIn("B4", review.rationale)
        self.assertIn("跟随错误", review.rationale)
        # 数值已能与修订表核对一致，不需再转人工核值，但是否跟随仍由规准决定。
        self.assertFalse(review.needs_teacher)

    def test_only_sequences_above_one_are_reviews(self):
        self.assertEqual(set(self.reviews), {"A3", "A6"})


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def test_feedback_contains_common_and_own_direction_sections(self):
        fb = build_feedback(self.repo, "S1")
        self.assertEqual(fb.direction, "设计方向")
        common_rubrics = {b.rubric for b in fb.common}
        direction_rubrics = {b.rubric for b in fb.directional}
        self.assertEqual(common_rubrics, {"R1", "R2"})
        self.assertEqual(direction_rubrics, {"R3"})
        text = fb.as_text()
        for heading in ("【共同反馈】", "【设计方向反馈】", "已证明", "可继续", "待补证据"):
            self.assertIn(heading, text)

    def test_feedback_names_signed_capacity_and_teacher(self):
        fb = build_feedback(self.repo, "S1")
        r2 = next(b for b in fb.common if b.rubric == "R2")
        self.assertEqual(r2.status, SIGNED)
        self.assertEqual(r2.signed_by, "教研组")

    def test_diverged_requirement_listed_as_research_pending(self):
        fb = build_feedback(self.repo, "S2")
        self.assertTrue(any("R1" in item for item in fb.pending_research))
        r1 = next(b for b in fb.common if b.rubric == "R1")
        self.assertNotEqual(r1.status, SIGNED)

    def test_evidence_gap_points_to_specific_fragment(self):
        fb = build_feedback(self.repo, "S2")
        r4 = next(b for b in fb.directional if b.rubric == "R4")
        self.assertIn("A4", r4.evidence_gap)


class StageRecordTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def test_no_student_merges_until_all_common_requirements_settled(self):
        record = build_stage_record(self.repo)
        self.assertEqual(record.merged_students, [])
        self.assertEqual(set(record.blocked), {"S1", "S2", "S3"})
        self.assertFalse(record.all_common_settled)

    def test_directional_pending_does_not_block_common_merge(self):
        # 用一个“共同项全签”的构造验证：方向附加待定只登记，不进阻断。
        from assessment.judgments import RequirementState
        import assessment.stage as stage_module

        original = stage_module.evaluate_student

        def fake_evaluate(repo, sid):
            states = original(repo, sid)
            for rid, state in states.items():
                if state.is_common:
                    state.status = SIGNED
                    state.signed_by = state.signed_by or "数学/专业"
                    state.caveats = []
            return states

        stage_module.evaluate_student = fake_evaluate
        try:
            record = build_stage_record(self.repo)
            # S2 的 R4 仍未定，登记在方向待定，但共同门槛已过（复核阻断另算）。
            self.assertIn("S2", record.direction_pending)
            common_blockers = [b for sid, items in record.blocked.items()
                               for b in items if "R4" in b]
            self.assertEqual(common_blockers, [])
        finally:
            stage_module.evaluate_student = original

    def test_comparison_view_separates_common_and_directional_lines(self):
        view = comparison_view(self.repo)
        self.assertNotIn("R5", view)  # 流程规准不进学生对比
        r3_students = {item["学生"] for item in view["R3"]["学生判断"]}
        self.assertEqual(r3_students, {"S1", "S3"})  # 仅设计方向
        r4_students = {item["学生"] for item in view["R4"]["学生判断"]}
        self.assertEqual(r4_students, {"S2"})       # 仅普通方向
        # 对比视图保留签定人与教研组待决标记。
        s2_r1 = next(i for i in view["R1"]["学生判断"] if i["学生"] == "S2")
        self.assertTrue(s2_r1["教研组待决"])


if __name__ == "__main__":
    unittest.main()
