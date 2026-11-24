"""规准版次澄清登记，以及对已发回结果的复核影响扫描。

同批一项规准被教研组澄清后，要能区分“只是表述变化”和“实际判准变化”：
只有判准变化才需要回看已发回的签定；表述变化保留原结果。
"""
from dataclasses import dataclass
import difflib

from .conventions import RUBRIC_CLARIFICATIONS, RESEARCH_GROUP


@dataclass(frozen=True)
class Clarification:
    rubric_id: str
    new_version: int
    criterion_changed: bool
    basis: str
    note: str

    @property
    def kind_text(self) -> str:
        return "实际判准变化" if self.criterion_changed else "仅表述变化"


REGISTERED_CLARIFICATIONS = [
    Clarification(
        rubric_id=item["规准"],
        new_version=item["新版次"],
        criterion_changed=item["criterion_changed"],
        basis=item["依据"],
        note=item["说明"],
    )
    for item in RUBRIC_CLARIFICATIONS
]


def wording_diff(repo, rubric_id: str, old_version: int, new_version: int) -> list[str]:
    """两版原文的逐行差异，供教研组核对变化落在哪句，不做语义自动裁决。"""
    old = repo.rubric_row(rubric_id, old_version)["原文"]
    new = repo.rubric_row(rubric_id, new_version)["原文"]
    return list(
        difflib.unified_diff(
            [old], [new], fromfile=f"{rubric_id}-{old_version}",
            tofile=f"{rubric_id}-{new_version}", lineterm="",
        )
    )


@dataclass
class ImpactItem:
    """一条可能需要复核的已发回结果。"""

    marking_id: str
    student: str
    rubric_ref: str
    reason: str
    re_review_required: bool


def impact_scan(repo) -> list[ImpactItem]:
    """扫描批语：哪些已发回/已签定结果引用了被判准变化的旧版次。"""
    impacts: list[ImpactItem] = []
    changed = {c.rubric_id: c for c in REGISTERED_CLARIFICATIONS if c.criterion_changed}
    for mark in repo.marking:
        rubric_id, _, version_text = mark["规准"].partition("-")
        if not version_text.isdigit():
            continue  # 如“春一”这类流程/阶段标记，与规准版次无关
        version = int(version_text)
        clar = changed.get(rubric_id)
        if clar is None or version >= clar.new_version:
            continue
        reason = (
            f"{rubric_id} 第 {version} 版已被第 {clar.new_version} 版取代，"
            f"登记为{clar.kind_text}：{clar.note}"
        )
        # 教研组按新版次作出的签定本身不需要复核；教师意见与已发回回执需要。
        by_research = mark["教师"] == RESEARCH_GROUP and mark["动作"] == "签定"
        impacts.append(
            ImpactItem(
                marking_id=mark["id"],
                student=mark["学生"],
                rubric_ref=mark["规准"],
                reason=reason,
                re_review_required=not by_research,
            )
        )
    return impacts


def re_review_required(repo) -> list[ImpactItem]:
    return [item for item in impact_scan(repo) if item.re_review_required]
