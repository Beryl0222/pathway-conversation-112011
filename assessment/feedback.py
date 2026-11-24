"""发给学生的反馈：共同反馈 + 本方向反馈。

每份反馈说明三件事：

1. 已经证明的能力（附支撑片段与签定人）；
2. 能在原来的推理上继续做什么（不推翻原推理，指出下一步）；
3. 还有哪一处证据需要补（指明片段编号与待补内容，不按文风评价）。
"""
from dataclasses import dataclass, field

from .judgments import (
    DIVERGED,
    NOT_STARTED,
    SIGNED,
    SINGLE_OPINION,
    evaluate_student,
)
from .evidence import CANNOT, PENDING, supports_for_student
from .resubmission import review_resubmissions


@dataclass
class FeedbackBlock:
    rubric: str
    requirement: str
    proven: str
    next_step: str
    evidence_gap: str
    status: str
    signed_by: str = ""
    research_pending: bool = False


@dataclass
class Feedback:
    student: str
    direction: str
    common: list[FeedbackBlock] = field(default_factory=list)
    directional: list[FeedbackBlock] = field(default_factory=list)
    pending_research: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [f"学生 {self.student}（{self.direction}）反馈", "=" * 36]
        lines.append("【共同反馈】")
        lines.extend(_render_blocks(self.common))
        lines.append("")
        lines.append(f"【{self.direction}反馈】")
        lines.extend(_render_blocks(self.directional))
        if self.pending_research:
            lines.append("")
            lines.append("【暂由教研组处理】")
            lines.extend(f"- {item}" for item in self.pending_research)
        return "\n".join(lines)


def _render_blocks(blocks: list[FeedbackBlock]) -> list[str]:
    if not blocks:
        return ["- 暂无适用要求"]
    out: list[str] = []
    for b in blocks:
        out.append(f"· {b.rubric} {b.requirement}（状态：{b.status}）")
        out.append(f"    已证明：{b.proven}")
        out.append(f"    可继续：{b.next_step}")
        out.append(f"    待补证据：{b.evidence_gap}")
        if b.signed_by:
            out.append(f"    签定：{b.signed_by}")
    return out


def _requirement_text(repo, rubric_id: str) -> str:
    for row in repo.rubrics:
        if row["id"] == rubric_id:
            return row["要求"]
    return rubric_id


def _proven_and_gap(repo, student: str, rubric: str):
    supports = [s for s in supports_for_student(repo, student) if s.rubric == rubric]
    proven_bits = [f"{s.answer_id}句{s.fragment_index + 1}：{s.reason}"
                   for s in supports if s.level == "可证明"]
    # 缺口只收“不能证明”或结论待审的片段；“可证明但归属待核”的保留提示见已证明栏，
    # 避免同一片段既算已证明又算待补。
    gaps = [f"{s.answer_id}句{s.fragment_index + 1}（{s.fragment_text[:18]}…）：{s.reason}"
            for s in supports
            if s.level in (CANNOT, PENDING)
            or (s.needs_review and s.level != "可证明")]
    return proven_bits, gaps


def build_feedback(repo, student_id: str) -> Feedback:
    direction = repo.students[student_id]["方向"]
    states = evaluate_student(repo, student_id)
    reviews = {r.answer_id: r for r in review_resubmissions(repo) if r.student == student_id}
    feedback = Feedback(student=student_id, direction=direction)

    for rubric, state in states.items():
        proven, gaps = _proven_and_gap(repo, student_id, rubric)
        requirement = _requirement_text(repo, rubric)
        if state.status == SIGNED:
            proven_text = "；".join(proven) or "已由负责方签定，见批语原文"
            next_step = _next_step(rubric, reviews)
            gap_text = "无强制待补；保留待审项供后续观察" if not gaps else "；".join(gaps)
        elif state.status in (DIVERGED,):
            proven_text = "两教师意见不一致，能力暂不定论"
            next_step = "等教研组裁定后再继续"
            gap_text = "；".join(gaps) or "教研组复核中"
        elif state.status in (SINGLE_OPINION, NOT_STARTED):
            proven_text = "；".join(proven) or "尚无足以签定的证据"
            next_step = "补齐独立复核意见后继续"
            gap_text = "；".join(gaps) or "缺第二责任方意见/缺直接证据"
        else:
            proven_text = "；".join(proven)
            next_step = "按教师审原文结论推进"
            gap_text = "；".join(gaps)

        block = FeedbackBlock(
            rubric=rubric, requirement=requirement,
            proven=proven_text, next_step=next_step, evidence_gap=gap_text,
            status=state.status, signed_by=state.signed_by,
            research_pending=state.research_pending,
        )
        (feedback.common if state.is_common else feedback.directional).append(block)
        if state.research_pending:
            feedback.pending_research.append(
                f"{rubric} {requirement}：两教师意见分歧，待教研组处理"
            )
    return feedback


def _next_step(rubric: str, reviews: dict) -> str:
    table = {
        "R1": "在原推理上补明每个数据来自哪次观测及个人实际承担的部分",
        "R2": "沿用既有方法替换为修订输入即可，不必重写推理链",
        "R3": "按已提方案完成可比较复测并回填观察记录",
        "R4": "在原比例式上补写分母为何包含这些点，并联系本次观察",
    }
    base = table.get(rubric, "在原推理上继续补充证据")
    frozen = [r for r in reviews.values() if r.input_unchanged]
    if frozen:
        base += "；前段已定评价保留，不重复计分"
    return base
