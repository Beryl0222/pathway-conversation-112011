"""算值核对、首错/跟随错误与证据支撑规则的测试。"""
import unittest

from assessment.repository import Repository
from assessment.scoring import (
    carried_error_answers,
    check_calculations,
    extract_claims,
    first_error_map,
)
from assessment.evidence import (
    CANNOT,
    PARTIAL,
    PENDING,
    PROVES,
    propose_supports,
    review_queue,
)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def claims(self, answer_id):
        return extract_claims(self.repo.answers[answer_id], self.repo)

    def test_s1_first_answer_arithmetic_wrong_against_source_table(self):
        # A1 的转写句与计算句都会产生主张，断言落在含算式的那条上。
        claim = next(c for c in self.claims("A1") if c.numerator is not None)
        self.assertEqual((claim.numerator, claim.denominator), (3, 8))
        self.assertEqual(claim.stated_value, 0.5)
        self.assertFalse(claim.arithmetic_ok)
        self.assertFalse(claim.matches_source)
        self.assertEqual(claim.expected_value, 3 / 8)

    def test_s2_revised_observation_value_is_checked_against_b4(self):
        # A6 主动换用修订表 B4：二除八 = 0.25，算式与来源都成立。
        calc_claims = [c for c in self.claims("A6") if c.numerator is not None]
        self.assertTrue(calc_claims)
        self.assertTrue(calc_claims[0].arithmetic_ok)
        self.assertTrue(calc_claims[0].matches_source)
        self.assertEqual(calc_claims[0].expected_value, 2 / 8)

    def test_value_without_source_is_not_auto_judged(self):
        # A5 没有引自，0.375 无法对照来源表，系统不自动判对错，转教师。
        claim, = self.claims("A5")
        self.assertIsNone(claim.matches_source)
        self.assertTrue(claim.note)

    def test_s3_half_claim_mismatches_three_eighths_source(self):
        # “伍成”按 0.5 核，来源表是 3/8，应判与来源不符。
        claim, = self.claims("A7")
        self.assertEqual(claim.stated_value, 0.5)
        self.assertFalse(claim.matches_source)

    def test_first_error_booked_once_and_carried_only_with_traceable_link(self):
        first = first_error_map(self.repo)
        self.assertEqual(first["S1"], "A1")
        carried = carried_error_answers(self.repo)
        # A2、A3 显式沿用 A1 的 0.5，列为跟随；A6 已换修订表，不在跟随列。
        self.assertEqual(carried["S1"], ["A2", "A3"])
        self.assertNotIn("A6", carried.get("S2", []))

    def test_check_calculations_covers_every_student_with_claims(self):
        result = check_calculations(self.repo)
        self.assertEqual(set(result), {"S1", "S2", "S3"})


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()

    def supports(self, answer_id, rubric):
        return [s for s in propose_supports(self.repo.answers[answer_id], self.repo)
                if s.rubric == rubric]

    def test_one_fragment_can_prove_design_but_not_observation_attribution(self):
        # A8 的已实施观察句：可支撑 R3 复测设计，但 R1 归属必须待审，结论可靠不被自动承认。
        r3 = self.supports("A8", "R3")
        r1 = self.supports("A8", "R1")
        self.assertTrue(any(s.level == PROVES for s in r3))
        self.assertTrue(all(s.level == PENDING for s in r1))

    def test_copying_guidebook_cannot_support_practice_requirements(self):
        for rubric in ("R1", "R2", "R4"):
            supports = self.supports("A4", rubric)
            self.assertTrue(supports)
            self.assertTrue(all(s.level == CANNOT for s in supports))

    def test_method_sentence_proves_reasoning_independent_of_wrong_value(self):
        # A2 的条件—建议推理可证明 R2 的推理侧面，数值错误在别处计，不重复奖惩。
        r2 = self.supports("A2", "R2")
        self.assertTrue(any(s.level == PROVES for s in r2))

    def test_transcription_only_partially_supports_r4(self):
        # 报分母点数只部分支撑 R4，是否解释分母构成需要教师另核，不自动签通过。
        supports = self.supports("A1", "R4")
        self.assertTrue(all(s.level in (PARTIAL, PENDING) for s in supports))

    def test_review_queue_collects_ambiguous_supports_for_teachers(self):
        queue = review_queue(self.repo, "S3")
        self.assertTrue(queue)
        self.assertTrue(all(item.needs_review for item in queue))
        # 待审项都带原文片段，教师可直接回查。
        self.assertTrue(all(item.fragment_text for item in queue))


if __name__ == "__main__":
    unittest.main()
