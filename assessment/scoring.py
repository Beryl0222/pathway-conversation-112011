"""算值正确性核对，以及“首错/跟随错误”的来源区分。

对应规准 R2：数值正确性与推理有效性分开评。后续方法成立但沿用同一前项
误值时，数值错误只计在首错处；照搬一个正确数的后续句不自动补足推理。
"""
from dataclasses import dataclass, field
import re

from .fragments import CALC, TRANSCRIBE, classify_answer
from .conventions import CN_DIGITS

_CN = "零〇一二两三四伍五六七八九十"
_CN_EXPR = re.compile(rf"([{_CN}]+)\s*除\s*([{_CN}]+)")
_ARAB_EXPR = re.compile(r"(\d+(?:\.\d+)?)\s*除\s*(\d+(?:\.\d+)?)")
_DECIMAL = re.compile(r"\d+\.\d+")
_HALF = re.compile(r"[伍五]成|一半")


@dataclass
class CalcClaim:
    """一条作答中的数值主张及其核对结论。"""

    answer_id: str
    text: str
    numerator: float | None = None
    denominator: float | None = None
    stated_value: float | None = None
    expected_value: float | None = None
    arithmetic_ok: bool | None = None      # 算式本身算得对不对
    matches_source: bool | None = None     # 输入是否与来源观测表一致
    basis: str = ""
    note: str = ""


def _cn(token: str) -> int | None:
    return CN_DIGITS.get(token) if not token.isdigit() else int(token)


def _expected_from_table(repo, answer_id: str) -> float | None:
    table = repo.table_for_chain(answer_id)
    return None if table is None else table.ratio


def extract_claims(answer: dict, repo) -> list[CalcClaim]:
    """从一条作答抽取数值主张并核对；抽不到输入就留空，转教师查原文。"""
    claims: list[CalcClaim] = []
    for frag in classify_answer(answer, repo):
        # 转写句也可能给出比例主张（如“占全部伍成”），同样纳入核对。
        if frag.kind not in (CALC, TRANSCRIBE):
            continue
        text = frag.text
        claim = CalcClaim(answer_id=answer["id"], text=text)
        m = _CN_EXPR.search(text) or _ARAB_EXPR.search(text)
        if m:
            claim.numerator = _cn(m.group(1)) if not m.group(1).isdigit() else float(m.group(1))
            claim.denominator = _cn(m.group(2)) if not m.group(2).isdigit() else float(m.group(2))
            claim.basis = "算式" + m.group(0)
        decimals = _DECIMAL.findall(text)
        if decimals:
            claim.stated_value = float(decimals[0])
            claim.basis = (claim.basis + "；" if claim.basis else "") + "作答给出的小数"
        elif _HALF.search(text):
            # “伍成/一半”按 0.5 核，保留原字，只在核对层换算。
            claim.stated_value = 0.5
            claim.basis = (claim.basis + "；" if claim.basis else "") + "“一半/伍成”按 0.5 核"
        expected = _expected_from_table(repo, answer["id"])
        claim.expected_value = expected
        if claim.numerator is not None and claim.denominator:
            computed = claim.numerator / claim.denominator
            claim.arithmetic_ok = (
                claim.stated_value is None
                or abs(computed - claim.stated_value) < 1e-9
            )
        if expected is not None and claim.stated_value is not None:
            claim.matches_source = abs(expected - claim.stated_value) < 1e-9
        if claim.arithmetic_ok is None and claim.matches_source is None:
            claim.note = "输入不完整，算值无法自动核对，转教师审原文"
        claims.append(claim)
    return claims


def check_calculations(repo) -> dict[str, list[CalcClaim]]:
    """按学生、按序次返回全部数值主张的核对结果。"""
    result: dict[str, list[CalcClaim]] = {}
    for student in repo.students:
        for answer in repo.answers_of(student):
            claims = extract_claims(answer, repo)
            if claims:
                result.setdefault(student, []).extend(claims)
    return result


def first_error_map(repo) -> dict[str, str]:
    """学生 -> 该生第一个算错（与来源表不符）的作答编号。

    后续作答沿用同一误值时，数值错误只计在这一首错处。
    """
    first_error: dict[str, str] = {}
    for student in repo.students:
        for answer in repo.answers_of(student):
            for claim in extract_claims(answer, repo):
                wrong = (
                    claim.matches_source is False
                    or (claim.arithmetic_ok is False)
                )
                if wrong and student not in first_error:
                    first_error[student] = answer["id"]
                    break
    return first_error


def carried_error_answers(repo) -> dict[str, list[str]]:
    """学生 -> 沿用首错误值、本身方法可另行评价的后续作答编号。

    判定要求显式可查：来源链指回首错所在作答，或文字明确声明沿用前值。
    无法证明沿用关系的不自动归入，留待教师判断。
    """
    first = first_error_map(repo)
    carried: dict[str, list[str]] = {}
    for student, error_id in first.items():
        ids: list[str] = []
        for answer in repo.answers_of(student):
            aid = answer["id"]
            if aid == error_id:
                continue
            upstream = repo.upstream_answers(aid)
            explicit = any(word in answer["文字"] for word in ("沿用", "用前面", "前面算", "前面是"))
            if error_id in upstream or explicit:
                ids.append(aid)
        if ids:
            carried[student] = ids
    return carried
