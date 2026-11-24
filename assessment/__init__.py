"""综合高中同一项目、两种升学方向的形成性评价整理包。

设计原则：

- 原始资料只读，所有判断都带片段编号、来源链和规则编号，可回查原文；
- 机器只做透明归类与流程校验，来源、归因或支撑程度有歧义一律转教师审原文，
  不依据文风自动判分；
- 教师批语是权威判断，机器提议（证据链、算值核对）只作整理与提示。
"""

from .conventions import (
    BRIEF_KIND,
    COMMON_TEACHERS,
    DIRECTION_OWNER,
    OBSERVATION_REVISIONS,
    PROCESS_RUBRICS,
)
from .repository import Repository, TableValues
from .fragments import Fragment, classify_answer, split_sentences
from .evidence import Support, propose_supports
from .scoring import CalcClaim, check_calculations, first_error_map
from .rubrics import Clarification, REGISTERED_CLARIFICATIONS, impact_scan
from .judgments import RequirementState, evaluate_student
from .resubmission import ResubmissionReview, review_resubmissions
from .feedback import build_feedback
from .stage import StageRecord, build_stage_record

__all__ = [
    "BRIEF_KIND",
    "COMMON_TEACHERS",
    "DIRECTION_OWNER",
    "OBSERVATION_REVISIONS",
    "PROCESS_RUBRICS",
    "Repository",
    "TableValues",
    "Fragment",
    "split_sentences",
    "classify_answer",
    "Support",
    "propose_supports",
    "CalcClaim",
    "check_calculations",
    "first_error_map",
    "Clarification",
    "REGISTERED_CLARIFICATIONS",
    "impact_scan",
    "RequirementState",
    "evaluate_student",
    "ResubmissionReview",
    "review_resubmissions",
    "build_feedback",
    "StageRecord",
    "build_stage_record",
]
