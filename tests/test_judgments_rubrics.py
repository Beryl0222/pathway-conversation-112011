"""签定权限、共同线独立复核与规准澄清影响的测试。"""
import unittest

from assessment.repository import Repository
from assessment.judgments import (
    DIVERGED,
    NOT_STARTED,
    SIGNED,
    SINGLE_OPINION,
    evaluate_student,
)
from assessment.rubrics import (
    REGISTERED_CLARIFICATIONS,
    impact_scan,
    re_review_required,
    wording_diff,
)
from assessment.conventions import PROCESS_RUBRICS


class JudgmentTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def test_common_line_requires_both_teachers_and_divergence_goes_to_research_group(self):
        s2 = evaluate_student(self.repo, "S2")
        # 两条意见立场无法由机器判定（其一明确要求教研组核实），保持分歧待教研组。
        self.assertEqual(s2["R1"].status, DIVERGED)
        self.assertTrue(s2["R1"].research_pending)

    def test_research_group_signature_settles_common_requirement(self):
        s1 = evaluate_student(self.repo, "S1")
        self.assertEqual(s1["R2"].status, SIGNED)
        self.assertEqual(s1["R2"].signed_by, "教研组")

    def test_directional_requirement_only_signed_by_owner_teacher(self):
        s1 = evaluate_student(self.repo, "S1")
        self.assertEqual(s1["R3"].status, SIGNED)
        self.assertEqual(s1["R3"].signed_by, "专业")
        # 普通方向学生不适用设计方向规准，反之亦然。
        self.assertNotIn("R3", evaluate_student(self.repo, "S2"))
        self.assertNotIn("R4", evaluate_student(self.repo, "S1"))

    def test_unauthorized_signature_is_recorded_as_opinion_only(self):
        # 班主任 M5 的对象/规准不是能力规准；构造越权场景校验权限提示。
        from assessment.judgments import _check_authority

        fake = {"id": "X1", "教师": "班主任", "对象": "A1", "规准": "R2-1",
                "动作": "签定", "原文": "越权签字"}
        view = _check_authority(fake, self.repo)
        self.assertFalse(view.authorized)
        self.assertIn("只作意见", view.authority_note)

    def test_single_opinion_does_not_settle_common_requirement(self):
        s1 = evaluate_student(self.repo, "S1")
        self.assertEqual(s1["R1"].status, NOT_STARTED)  # S1 的 R1 完全没有批语
        s3 = evaluate_student(self.repo, "S3")
        self.assertEqual(s3["R1"].status, NOT_STARTED)

    def test_process_rubric_excluded_from_student_states(self):
        for sid in self.repo.students:
            self.assertTrue(PROCESS_RUBRICS.isdisjoint(evaluate_student(self.repo, sid)))

    def test_receipt_does_not_change_capacity_state(self):
        # M5 是“已回执”，不应让任何要求凭空变成已签定。
        for sid in self.repo.students:
            for state in evaluate_student(self.repo, sid).values():
                if state.status == SIGNED:
                    self.assertNotEqual(state.signed_by, "班主任")


class RubricClarificationTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def test_r2_change_registered_as_criterion_change(self):
        clar = next(c for c in REGISTERED_CLARIFICATIONS if c.rubric_id == "R2")
        self.assertTrue(clar.criterion_changed)
        self.assertEqual(clar.new_version, 2)

    def test_wording_diff_points_to_changed_sentence(self):
        diff = wording_diff(self.repo, "R2", 1, 2)
        self.assertTrue(any("跟随错误" in line for line in diff))

    def test_impact_scan_flags_old_version_results_but_not_new_research_signature(self):
        impacted_ids = {item.marking_id for item in impact_scan(self.repo)}
        self.assertIn("M1", impacted_ids)
        self.assertIn("M2", impacted_ids)
        required = {item.marking_id for item in re_review_required(self.repo)}
        # 教研组对同一旧版次的定案本身不需复核；两条教师意见需要。
        self.assertIn("M1", required)
        self.assertNotIn("M3", required)

    def test_wording_only_change_would_not_trigger_review(self):
        # 登记为仅表述变化时，impact_scan 不会产出复核项。
        from assessment.rubrics import Clarification
        import assessment.rubrics as rubrics_module

        original = rubrics_module.REGISTERED_CLARIFICATIONS
        rubrics_module.REGISTERED_CLARIFICATIONS = [
            Clarification("R1", 2, False, "仅措辞", "表述变化")
        ]
        try:
            self.assertEqual(re_review_required(self.repo), [])
        finally:
            rubrics_module.REGISTERED_CLARIFICATIONS = original


if __name__ == "__main__":
    unittest.main()
