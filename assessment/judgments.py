"""按学生×规准汇总签定状态，并校验签定权限与顺序。

规则对应 R5 与业务约定：

- 两位教师只能签自己负责的要求；越权签字只登记为意见，不算签定；
- 共同要求由数学、专业教师独立出意见，不一致交教研组；教研组未处理前
  状态保持“分歧待教研组”，不能汇入阶段记录；
- 方向附加能力由对应方向负责教师签定，其他教师签字只作意见；
- 第一次已签的共同能力可同时供两个方向引用，方向附加项各自判定。
"""
from dataclasses import dataclass, field

from .conventions import (
    COMMON_TEACHERS,
    DIRECTION_OWNER,
    PROCESS_RUBRICS,
    RESEARCH_GROUP,
)

# 状态枚举。
NOT_STARTED = "未开始"
SINGLE_OPINION = "仅单方意见"
INDEPENDENT_DONE = "两教师独立意见已齐"
DIVERGED = "分歧待教研组"
SIGNED = "已签定"
REVIEW_PENDING = "待教师审原文"


@dataclass
class MarkView:
    """一条批语经权限校验后的视图。"""

    marking_id: str
    teacher: str
    objects: list[str]
    rubric: str
    version: int
    action: str
    text: str
    authorized: bool
    authority_note: str


@dataclass
class RequirementState:
    student: str
    rubric: str
    level: str                 # 共同 / 设计方向 / 普通方向
    status: str
    marks: list[MarkView] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    signed_by: str = ""
    research_pending: bool = False

    @property
    def is_common(self) -> bool:
        return self.level == "共同"

    @property
    def settled(self) -> bool:
        """共同要求只有已签定才算处理完；方向线由负责教师签定为 settled。"""
        return self.status == SIGNED


def _rubric_level(repo, rubric_id: str) -> str:
    for row in repo.rubrics:
        if row["id"] == rubric_id:
            return row["层级"]
    raise KeyError(rubric_id)


def _check_authority(mark: dict, repo) -> MarkView:
    rubric_id, version = repo.parse_ref(mark["规准"]) if "-" in mark["规准"] else (mark["规准"], 0)
    level = _rubric_level(repo, rubric_id) if any(r["id"] == rubric_id for r in repo.rubrics) else "流程"
    teacher = mark["教师"]
    authorized = True
    note = ""
    if teacher == RESEARCH_GROUP:
        authorized = True
    elif level == "共同":
        authorized = teacher in COMMON_TEACHERS
        if not authorized:
            note = f"{teacher} 非共同线负责教师，该签字只作意见"
    elif level in DIRECTION_OWNER:
        owner = DIRECTION_OWNER[level]
        authorized = teacher == owner
        if not authorized:
            note = f"{level} 由{owner}签定，{teacher} 的签字只作意见"
    else:
        authorized = False
        note = "流程/阶段标记不产生能力签定"
    # 动作本身不是“签定”的，即使有权限也只是意见。
    if mark["动作"] != "签定":
        note = (note + "；" if note else "") + f"动作={mark['动作']}，记为意见或回执"
    return MarkView(
        marking_id=mark["id"], teacher=teacher, objects=repo.objects_of(mark),
        rubric=rubric_id, version=version, action=mark["动作"],
        text=mark["原文"], authorized=authorized and mark["动作"] == "签定",
        authority_note=note,
    )


def _opinion_stance(mark_views: list[MarkView]) -> tuple[bool, str]:
    """两位共同线教师意见是否一致，以及一致时的立场（肯定/否定）。

    这只是辅助整理，最终分歧由教研组裁定；任一方措辞无法确定时按分歧处理
    并转教师审原文，系统不替教师解读语义。
    """
    positive_words = ("认可", "通过", "可讲清", "可继续", "同意")
    negative_words = ("算错", "错误", "不能", "没有", "缺", "只重复", "未", "无")

    def stance(text: str) -> str | None:
        if any(word in text for word in positive_words):
            # 同句既指出错误又认可方法时，以是否含明确否定词再细分。
            return "否定" if any(w in text for w in negative_words) else "肯定"
        if any(word in text for word in negative_words):
            return "否定"
        return None

    common = [mv for mv in mark_views if mv.teacher in COMMON_TEACHERS]
    stances = [stance(mv.text) for mv in common]
    if len(stances) != 2 or any(s is None for s in stances):
        return False, "意见措辞无法自动判定立场，转教研组/教师审原文"
    if stances[0] != stances[1]:
        return False, "两教师立场不一致，交教研组处理"
    # 立场一致：肯定才可签通过；一致否定说明该要求未达标，保持未定并注明。
    if stances[0] == "否定":
        return False, "两教师一致认为现有证据不足以通过，退回补证据"
    return True, "两教师独立意见一致肯定"


def evaluate_student(repo, student_id: str) -> dict[str, RequirementState]:
    """生成该学生在每条适用规准上的要求状态（流程规准除外）。"""
    direction = repo.students[student_id]["方向"]
    applicable = [
        row for row in repo.rubrics
        if row["id"] not in PROCESS_RUBRICS
        and (row["层级"] == "共同" or row["层级"] == direction)
        and row["版次"] == repo.latest_rubric_version(row["id"])
    ]
    states: dict[str, RequirementState] = {}
    marks = [m for m in repo.marking_for(student_id)]
    for row in applicable:
        rid = row["id"]
        level = row["层级"]
        related = [_check_authority(m, repo) for m in marks if m["规准"].split("-")[0] == rid]
        state = RequirementState(student=student_id, rubric=rid, level=level,
                                 status=NOT_STARTED, marks=related)
        for mv in related:
            if mv.authority_note:
                state.caveats.append(f"[{mv.marking_id}] {mv.authority_note}")
        _fill_status(state, related)
        states[rid] = state
    return states


def _fill_status(state: RequirementState, related: list[MarkView]) -> None:
    # 教研组签定直接定案（共同线分歧的最终处理）。
    rg = [mv for mv in related if mv.teacher == RESEARCH_GROUP and mv.action == "签定"]
    if rg:
        state.status = SIGNED
        state.signed_by = RESEARCH_GROUP
        return
    authorized_signs = [mv for mv in related if mv.authorized]
    if state.level == "共同":
        opinions = [mv for mv in related if mv.teacher in COMMON_TEACHERS]
        teachers = {mv.teacher for mv in opinions}
        if authorized_signs:
            # 共同线任一负责教师直接“签定”也需另一线独立复核，缺一不收口。
            pass
        if teachers == set(COMMON_TEACHERS):
            agreed, note = _opinion_stance(related)
            state.caveats.append(note)
            if agreed:
                state.status = SIGNED
                state.signed_by = "/".join(COMMON_TEACHERS)
            else:
                state.status = DIVERGED
                state.research_pending = "交教研组" in note or "无法自动判定" in note
        elif teachers:
            state.status = SINGLE_OPINION
        return
    # 方向线：负责教师签定即收口。
    if authorized_signs:
        state.status = SIGNED
        state.signed_by = authorized_signs[0].teacher
    elif related:
        state.status = SINGLE_OPINION
