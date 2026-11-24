"""把句子片段映射到它“能证明什么、不能证明什么”。

关键约束（对应业务约定）：

- 一项能力可由不同路径成立（先估算后推论，或先布置后用观察修正）；
- 一个片段可以同时证明“表达清楚”而不能证明“结论可靠”，支撑按要求逐条列；
- 抄题/转述、只有小组记录的句子不能自动支持个人实践类要求；
- 来源、归因或支撑程度有歧义的，只生成待审项，不替教师下结论。
"""
from dataclasses import dataclass, field

from .fragments import (
    CALC,
    COPY,
    GROUP,
    INTENT,
    METHOD,
    OBSERVATION,
    REVIEW,
    TRANSCRIBE,
    classify_answer,
)

# 规准编号 -> 该要求实际考查的能力侧面。
REQUIREMENT_FACETS = {
    "R1": "可回查观测与个人归因",
    "R2": "数值正确与推理有效（分开评）",
    "R3": "改变布置后的可比较复测设计",
    "R4": "联系本次观察解释比例分母",
}

# 支撑强度。
PROVES = "可证明"
PARTIAL = "部分支撑"
CANNOT = "不能证明"
PENDING = "待教师审原文"


@dataclass
class Support:
    """一个片段对一条规准的支撑判断。"""

    answer_id: str
    fragment_index: int
    fragment_text: str
    rubric: str
    level: str
    reason: str
    needs_review: bool = False


# 不同片段类型对各规准的默认支撑关系。值为 (强度, 理由)；
# 一条片段因此可以对 R3 可证明、对 R1 不能证明，互不冲销。
_DEFAULT_SUPPORT = {
    TRANSCRIBE: {
        "R1": (PARTIAL, "点数陈述带来源表，可证明观测来源；个人归因仍要看同段分工说明"),
        "R2": (PARTIAL, "提供输入数据，但只报值不足以证明方法"),
        "R4": (PARTIAL, "出现分母点数，但是否解释分母构成需另看推理句"),
    },
    CALC: {
        "R2": (PARTIAL, "有独立计算意图；数值正确性由算值核对另行判断，不能由句子自证"),
        "R4": (PARTIAL, "出现除法结构；是否联系本次观察解释分母需教师核"),
    },
    METHOD: {
        "R2": (PROVES, "条件—建议式推理可证明推理有效，数值对错不在本句重复计"),
        "R3": (PARTIAL, "提出布置调整与复测思路；区分方案与已实施观察需另核"),
        "R4": (PARTIAL, "若涉及分母选择可部分支撑，需确认是否联系本次观察"),
    },    OBSERVATION: {
        "R1": (PENDING, "已实施观察的归属与可回查性必须对照来源表，转教师核"),
        "R3": (PROVES, "陈述已实施的可重复观察动作，可支撑复测设计的实施侧面"),
    },
    INTENT: {
        "R3": (CANNOT, "仅为意图自述，尚未实施，不能当作已完成的复测表现"),
    },
    COPY: {
        "R1": (CANNOT, "抄录/转述指导书没有本次观测归属，不能支持可回查观测"),
        "R4": (CANNOT, "引用规准示例但未联系本次观察，按 R4 不能签为通过"),
        "R2": (CANNOT, "照搬示例不构成自己的数值或推理表现"),
    },
    GROUP: {
        "R1": (PENDING, "只有小组记录时个人实践归因按校方约定需教师区分，不能直接计个人"),
    },
    REVIEW: {
        "R1": (PENDING, "归类依据不足，支撑程度转教师审原文"),
        "R2": (PENDING, "归类依据不足，支撑程度转教师审原文"),
    },
}


def propose_supports(answer: dict, repo, rubric_ids=("R1", "R2", "R3", "R4")) -> list[Support]:
    """逐片段生成对各规准的支撑提议；机器不下通过结论，只整理证据与待审项。"""
    supports: list[Support] = []
    for frag in classify_answer(answer, repo):
        table = _DEFAULT_SUPPORT.get(frag.kind, {})
        for rubric in rubric_ids:
            if rubric not in table:
                continue
            level, reason = table[rubric]
            # 同一句既含算式/数值又含条件推理连接时，允许它同时支撑推理侧面：
            # 数值正确性仍由算值核对另计，不因句子带数就自动算推理达标。
            if (frag.kind == CALC and rubric == "R2"
                    and any(w in frag.text for w in ("不足", "若", "因为", "所以", "才", "就"))):
                level, reason = PROVES, "含条件—应用推理，可证明推理有效；数值对错另行核对不重复计"
            needs_review = frag.needs_review or level == PENDING
            if frag.needs_review and frag.review_reason:
                reason = f"{reason}；{frag.review_reason}"
            supports.append(
                Support(
                    answer_id=answer["id"],
                    fragment_index=frag.index,
                    fragment_text=frag.text,
                    rubric=rubric,
                    level=level,
                    reason=reason,
                    needs_review=needs_review,
                )
            )
    return supports


def supports_for_student(repo, student_id: str) -> list[Support]:
    out: list[Support] = []
    for answer in repo.answers_of(student_id):
        out.extend(propose_supports(answer, repo))
    return out


def review_queue(repo, student_id: str | None = None) -> list[Support]:
    """所有需要教师看原文才能定的支撑项，按学生归集。"""
    students = [student_id] if student_id else list(repo.students)
    queue: list[Support] = []
    for sid in students:
        queue.extend(s for s in supports_for_student(repo, sid) if s.needs_review)
    return queue
