"""补交分段与观测修订的处理规则。

两条核心约定：

1. 学生只有后续分段补交、前段采用的输入没有变时，前段已定评价保留，
   后段既不被重复奖惩，也不因前一步改对而自动达标；
2. 若经核准的观测被重订，引用原值的后续作答是否仍按“跟随错误”处理，
   不自动改判，而由后一项实际所用材料与适用规准版次决定。
"""
from dataclasses import dataclass, field

from .scoring import carried_error_answers, extract_claims, first_error_map
from .rubrics import REGISTERED_CLARIFICATIONS


@dataclass
class ResubmissionReview:
    student: str
    answer_id: str
    segment: str
    seq: int
    prior_answer_id: str
    input_unchanged: bool
    prior_decisions_frozen: list[str]
    treatment: str
    rationale: str
    needs_teacher: bool = False


def _same_segment_priors(repo, answer: dict) -> list[dict]:
    return [
        row for row in repo.answers_of(answer["学生"])
        if row["分段"] == answer["分段"] and row["序次"] < answer["序次"]
    ]


def review_resubmissions(repo) -> list[ResubmissionReview]:
    """对所有序次大于 1 的补交分段给出处理意见。"""
    first_error = first_error_map(repo)
    carried = carried_error_answers(repo)
    reviews: list[ResubmissionReview] = []
    for student in repo.students:
        for answer in repo.answers_of(student):
            if answer["序次"] <= 1:
                continue
            priors = _same_segment_priors(repo, answer)
            reviews.append(
                _review_one(repo, answer, priors, first_error.get(student),
                            carried.get(student, []))
            )
    return reviews


def _review_one(repo, answer, priors, first_error_id, carried_ids) -> ResubmissionReview:
    student = answer["学生"]
    aid = answer["id"]
    # 前段输入是否变化：比较来源链上的观测表是否相同。
    prior_sources = {s for p in priors for s in repo.source_briefs(p["id"])}
    now_sources = set(repo.source_briefs(aid))
    input_unchanged = bool(prior_sources) and now_sources == prior_sources

    frozen: list[str] = []
    prior_ids = {p["id"] for p in priors}
    for mark in repo.marking_for(student):
        # 只冻结明确指向前段作答的批语；跨段/阶段回执不冒充前段能力签定。
        if prior_ids and set(repo.objects_of(mark)).issubset(prior_ids):
            frozen.append(mark["id"])

    uses_revised = any(
        repo.revised_from(brief) is not None for brief in repo.source_briefs(aid)
    )

    if input_unchanged:
        treatment = "保留前段已定评价，后段独立评方法，不重复计数值错误"
        rationale = (
            "补交仅发生在后段且来源观测未变；前段签定冻结，"
            "后段沿用同一误值按跟随错误处理，数值错误只记首错"
            if aid in carried_ids
            else "补交仅发生在后段且来源观测未变；前段签定冻结，后段按自身证据评价"
        )
        return ResubmissionReview(student, aid, answer["分段"], answer["序次"],
                                  priors[-1]["id"] if priors else "", True, frozen,
                                  treatment, rationale)

    if uses_revised:
        # 重订了经核准的观测：是否仍按跟随错误，取决于后续所用材料与规准。
        new_briefs = [b for b in repo.source_briefs(aid) if repo.revised_from(b)]
        r2_changed = any(c.rubric_id == "R2" and c.criterion_changed
                         for c in REGISTERED_CLARIFICATIONS)
        claims = extract_claims(answer, repo)
        value_ok = all(c.matches_source is not False and c.arithmetic_ok is not False
                       for c in claims) if claims else False
        treatment = "不自动改判；按后续实际所用修订表与新版规准重新评定"
        rationale = (
            f"来源改用经核准修订观测 {', '.join(new_briefs)}，"
            f"R2 已登记为判准变化={r2_changed}。后段算值与来源核对结果："
            f"{'数值与修订表一致' if value_ok else '仍需教师核对'}；"
            "是否仍按跟随错误须由后项材料与规准决定，前段旧观测上的签定仍然保留"
        )
        return ResubmissionReview(student, aid, answer["分段"], answer["序次"],
                                  priors[-1]["id"] if priors else "", False, frozen,
                                  treatment, rationale, needs_teacher=not value_ok)

    return ResubmissionReview(
        student, aid, answer["分段"], answer["序次"],
        priors[-1]["id"] if priors else "", False, frozen,
        "来源发生变化但未登记为核准修订，转教师审原文",
        "补交段引用来源与前段不同，且不在学校观测修订登记内，不能自动套用跟随错误",
        needs_teacher=True,
    )
