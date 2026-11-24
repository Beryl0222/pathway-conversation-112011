"""分段作答的句子切分与透明归类。

每条作答保留原句，归类只依据显式信号（引自哪张表、数字算式、约定的
小组/个人标记、意图词），每条结论附规则编号。任何无法用显式信号确定的
句子标 ``待审``，由教师看原文，系统不按文风判分。
"""
from dataclasses import dataclass, field
import re

from .conventions import (
    BRIEF_KIND,
    GROUP_ONLY_MARKERS,
    INTENT_MARKERS,
    PERSONAL_PRACTICE_MARKERS,
)

# 归类标签：抄题/转述指导书、图表转写、计算、方法推理、已实施观察、
# 意图自述、小组归属、待审。
COPY = "抄题转述"
TRANSCRIBE = "图表转写"
CALC = "计算陈述"
METHOD = "方法推理"
OBSERVATION = "已实施观察"
INTENT = "意图自述"
GROUP = "小组归属"
REVIEW = "待审"

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])")
_POINT_COUNT = re.compile(r"[0-9一二两三四伍五六七八九十]+\s*个?点|[伍五]成|一半")


@dataclass
class Fragment:
    """作答中的一个句子及其归类证据。"""

    answer_id: str
    index: int
    text: str
    kind: str
    rule: str
    needs_review: bool = False
    review_reason: str = ""
    source_refs: list[str] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    """按中文句读切分，保留原文用字（含异体字、省略），不做改写。"""
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _overlap_ratio(short: str, long: str) -> float:
    if not short:
        return 0.0
    shared = sum(1 for ch in short if ch in long)
    return shared / len(short)


def classify_answer(answer: dict, repo) -> list[Fragment]:
    """对一条作答逐句归类。``repo`` 提供资料原文与类别以核对抄录关系。"""
    aid = answer["id"]
    ref = answer.get("引自", "")
    ref_brief = repo.briefs.get(ref)
    out: list[Fragment] = []
    for index, sentence in enumerate(split_sentences(answer["文字"])):
        out.append(_classify_one(aid, index, sentence, ref, ref_brief, repo))
    return out


def _classify_one(aid, index, text, ref, ref_brief, repo) -> Fragment:
    # 1. 小组/个人贡献约定：显式标记，区分小组记录与个人实践。
    if any(mark in text for mark in GROUP_ONLY_MARKERS):
        personal = any(mark in text for mark in PERSONAL_PRACTICE_MARKERS)
        if personal:
            return Fragment(aid, index, text, GROUP, "G2-小组记录且声明个人分工",
                            needs_review=True,
                            review_reason="同句含小组与个人信号，个人实践范围需教师核原文",
                            source_refs=[ref] if ref else [])
        return Fragment(aid, index, text, GROUP, "G1-仅有小组记录",
                        source_refs=[ref] if ref else [])

    # 2. 抄题/转述：逐字命中所引资料才判抄录。指导书类抄录不能支持实践要求；
    #    对指导书的非逐字高重合句判“转述”，先于计算规则，避免把背书当成自己的算式。
    if ref_brief is not None and text in ref_brief["原文"]:
        review = BRIEF_KIND.get(ref) == "指导书"
        reason = "指导书示例不联系本次观察，不能据此签实践类要求" if review else ""
        return Fragment(aid, index, text, COPY, "C1-与所引资料逐字相同",
                        review, reason, [ref])
    if (ref_brief is not None and BRIEF_KIND.get(ref) == "指导书"
            and _overlap_ratio(text, ref_brief["原文"]) >= 0.5):
        return Fragment(aid, index, text, COPY, "C2-转述指导书示例",
                        needs_review=True,
                        review_reason="非逐字引用指导书，是否联系本次观察需教师核原文",
                        source_refs=[ref])

    # 3. 计算陈述：出现算式或小数结果（先于意图，避免“先换……为 0.25”漏判）。
    if "除" in text or re.search(r"[0-9]\.[0-9]", text):
        return Fragment(aid, index, text, CALC, "X1-含算式或数值结果",
                        source_refs=[ref] if ref else [])

    # 4. 图表转写：单纯陈述点数且来源链落到观测表。
    #    “记录了 N 点/N 个达标”是点数转写；只有明确的观察/布置动作才归已实施观察。
    action_words = ("观察", "复测", "再测", "遮挡", "降了", "放在", "我把")
    has_action = any(mark in text for mark in action_words)
    if (not has_action and _POINT_COUNT.search(text)
            and repo.table_for_chain(aid) is not None):
        return Fragment(aid, index, text, TRANSCRIBE, "T1-点数陈述且来源为观测表",
                        source_refs=repo.source_briefs(aid))

    # 5. 非逐字但与所引资料高度重合：判转述并转教师，不自动当作学生自己的表述。
    if ref_brief is not None and _overlap_ratio(text, ref_brief["原文"]) >= 0.7:
        return Fragment(aid, index, text, COPY, "C3-转述所引资料",
                        needs_review=True,
                        review_reason="非逐字引用，转述是否联系本次观察需教师核原文",
                        source_refs=[ref])

    # 6. 已实施观察：出现已发生的观察/布置动作词（即使同句含点数或推理连接）。
    if has_action:
        return Fragment(aid, index, text, OBSERVATION, "O1-陈述已实施观察",
                        needs_review=True,
                        review_reason="观察归属与可回查性需教师对照来源表确认",
                        source_refs=[ref] if ref else [])

    # 7. 意图自述：只说打算做什么，不能算已实施观察。
    if any(mark in text for mark in INTENT_MARKERS):
        return Fragment(aid, index, text, INTENT, "I1-意图自述非已实施",
                        source_refs=[ref] if ref else [])

    # 8. 方法推理：含条件、建议、比较等推理连接。
    if any(mark in text for mark in ("因为", "所以", "若", "即使", "看", "建议", "用")):
        return Fragment(aid, index, text, METHOD, "M1-条件或建议推理",
                        source_refs=[ref] if ref else [])

    # 9. 无法用显式信号确定，绝不靠文风猜测。
    return Fragment(aid, index, text, REVIEW, "U1-无显式信号",
                    needs_review=True, review_reason="归类依据不足，转教师审原文")
