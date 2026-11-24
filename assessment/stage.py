"""阶段记录汇入门槛与跨方向对比视图。

学校只在某学生的所有共同要求都已处理（已签定、无教研组待决）后，才把该生
汇入共用的阶段记录；方向附加项未定不阻断共同汇入，但只在对应方向保留待定。
"""
from dataclasses import dataclass, field

from .conventions import PROCESS_RUBRICS
from .judgments import DIVERGED, SIGNED, evaluate_student
from .rubrics import re_review_required


@dataclass
class StageRecord:
    stage: str
    merged_students: list[str] = field(default_factory=list)
    blocked: dict[str, list[str]] = field(default_factory=dict)
    direction_pending: dict[str, list[str]] = field(default_factory=dict)

    @property
    def all_common_settled(self) -> bool:
        return not self.blocked


def _common_requirement_ids(repo) -> list[str]:
    ids = sorted({r["id"] for r in repo.rubrics if r["层级"] == "共同"})
    # 流程规约束签定流程，不是学生能力项，不进汇入门槛。
    return [rid for rid in ids if rid not in PROCESS_RUBRICS]


def build_stage_record(repo, stage: str | None = None) -> StageRecord:
    common_ids = _common_requirement_ids(repo)
    pending_re_review = {item.student for item in re_review_required(repo)}
    record = StageRecord(stage=stage or next(iter(repo.students.values()))["阶段"])

    for student_id, info in repo.students.items():
        if stage is not None and info["阶段"] != stage:
            continue
        states = evaluate_student(repo, student_id)
        blockers: list[str] = []
        for rid in common_ids:
            state = states.get(rid)
            if state is None or state.status != SIGNED:
                blockers.append(f"{rid} 状态={state.status if state else '无记录'}")
        if student_id in pending_re_review:
            blockers.append("存在判准变化后需复核的已发回结果")
        if blockers:
            record.blocked[student_id] = blockers
        else:
            record.merged_students.append(student_id)

        pending_direction = [
            f"{rid} 状态={state.status}"
            for rid, state in states.items()
            if not state.is_common and state.status != SIGNED
        ]
        if pending_direction:
            record.direction_pending[student_id] = pending_direction
    return record


def comparison_view(repo) -> dict[str, dict]:
    """教师打开同一份作业时的跨方向对比：共同判断 + 两方向各自判断。

    返回按规准编号组织的视图，标明层级、各相关学生的状态、签定人与待决项，
    使教师能比较两个方向的判断、原批语与修订理由。
    """
    view: dict[str, dict] = {}
    for row in repo.rubrics:
        rid = row["id"]
        if rid in PROCESS_RUBRICS:
            continue  # 流程规准不面向学生能力展示
        view.setdefault(rid, {
            "要求": row["要求"], "层级": row["层级"],
            "最新版次": repo.latest_rubric_version(rid), "学生判断": [],
        })
    for student_id, info in repo.students.items():
        for rid, state in evaluate_student(repo, student_id).items():
            view[rid]["学生判断"].append({
                "学生": student_id,
                "方向": info["方向"],
                "状态": state.status,
                "签定人": state.signed_by,
                "教研组待决": state.research_pending,
                "权限提示": state.caveats,
            })
    return view
