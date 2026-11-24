"""只读资料仓储：装载交接 JSON，建索引与来源链，抽取观测表数值。

原始记录保持录入顺序与文字原样，仓储只增加可回查的派生索引，
绝不改写 data/ 下任何字段。
"""
from dataclasses import dataclass
import re
from pathlib import Path

from corpus import read_collection
from .conventions import BRIEF_KIND, OBSERVATION_REVISIONS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_NUM = r"[0-9]+(?:\.[0-9]+)?"
_DADA = re.compile(rf"({_NUM})\s*个达标点|达标点[^0-9]*?({_NUM})\s*个")
_JILU = re.compile(rf"({_NUM})\s*个记录点|记录点[^0-9]*?({_NUM})\s*个")
# 作答里“三除八”“二除八”等中文数字算式。
_CN = "零〇一二两三四伍五六七八九十"
_CN_EXPR = re.compile(rf"([{_CN}]+)\s*除\s*([{_CN}]+)")
_ARAB_EXPR = re.compile(rf"({_NUM})\s*/\s*({_NUM})|({_NUM})\s*除\s*({_NUM})")
_DECIMAL = re.compile(rf"(?<![0-9.])({_NUM})(?![0-9.])")


@dataclass(frozen=True)
class TableValues:
    """一张观测表中可核的点数；抽取失败留 None，交教师查原文。"""

    source_id: str
    qualified: int | None
    total: int | None

    @property
    def ratio(self) -> float | None:
        if self.qualified is None or not self.total:
            return None
        return self.qualified / self.total


def _extract_int(pattern: re.Pattern, text: str) -> int | None:
    match = pattern.search(text)
    if not match:
        return None
    # 兼容“2 个达标点”与“达标点修订为 2 个”两种句式（两个捕获组择一）。
    return int(next(group for group in match.groups() if group is not None))


class Repository:
    """封装五份交接资料的只读访问。"""

    def __init__(self, directory: Path | str = DATA_DIR):
        self.directory = Path(directory)
        self.briefs = {r["id"]: r for r in read_collection(self.directory / "briefs.json")}
        self.answers = {r["id"]: r for r in read_collection(self.directory / "answers.json")}
        self.rubrics = read_collection(self.directory / "rubrics.json")
        self.marking = read_collection(self.directory / "marking.json")
        self.students = {r["id"]: r for r in read_collection(self.directory / "students.json")}
        self.tables = self._extract_tables()
        self._answer_order = self._order_answers()

    # ---- 基本索引 -----------------------------------------------------
    def _extract_tables(self) -> dict[str, TableValues]:
        tables: dict[str, TableValues] = {}
        for bid, row in self.briefs.items():
            if BRIEF_KIND.get(bid) not in ("观测表", "观测表修订"):
                continue
            tables[bid] = TableValues(
                source_id=bid,
                qualified=_extract_int(_DADA, row["原文"]),
                total=_extract_int(_JILU, row["原文"]),
            )
        return tables

    def _order_answers(self) -> dict[str, list[str]]:
        order: dict[str, list[str]] = {}
        for aid, row in self.answers.items():
            order.setdefault(row["学生"], []).append(aid)
        for ids in order.values():
            ids.sort(key=lambda aid: (self.answers[aid]["分段"], self.answers[aid]["序次"]))
        return order

    def answers_of(self, student_id: str) -> list[dict]:
        return [self.answers[aid] for aid in self._answer_order.get(student_id, [])]

    def latest_rubric_version(self, rubric_id: str) -> int:
        return max(r["版次"] for r in self.rubrics if r["id"] == rubric_id)

    def rubric_row(self, rubric_id: str, version: int) -> dict:
        for row in self.rubrics:
            if row["id"] == rubric_id and row["版次"] == version:
                return row
        raise KeyError(f"规准版次不存在：{rubric_id}-{version}")

    def marking_for(self, student_id: str) -> list[dict]:
        return [m for m in self.marking if m["学生"] == student_id]

    def objects_of(self, marking_row: dict) -> list[str]:
        """批语对象字段可能是 A1 或 A1/A2，展开为作答编号。"""
        return [part for part in marking_row["对象"].split("/") if part]

    def parse_ref(self, ref: str) -> tuple[str, int]:
        """把 R2-1 这样的规准引用拆成 (规准编号, 版次)。"""
        rubric_id, _, version = ref.partition("-")
        return rubric_id, int(version)

    # ---- 来源链 -------------------------------------------------------
    def provenance_chain(self, answer_id: str) -> list[str]:
        """沿“引自”向上回溯到资料或更早作答，带环保护，全部编号可回查。"""
        chain: list[str] = []
        current = answer_id
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            chain.append(current)
            if current in self.briefs:
                break
            row = self.answers.get(current)
            if row is None:
                chain.append(f"未登记来源:{current}")
                break
            current = row.get("引自", "")
        return chain

    def source_briefs(self, answer_id: str) -> list[str]:
        """该作答（含其引用的上游作答）最终落到哪些资料编号。"""
        return [node for node in self.provenance_chain(answer_id) if node in self.briefs]

    def upstream_answers(self, answer_id: str) -> list[str]:
        return [node for node in self.provenance_chain(answer_id) if node in self.answers]

    def revised_from(self, brief_id: str) -> str | None:
        """若该资料是修订稿，返回其替代的原稿编号。"""
        return OBSERVATION_REVISIONS.get(brief_id)

    # ---- 图表转写核对 -------------------------------------------------
    def table_for_chain(self, answer_id: str) -> TableValues | None:
        """来源链上的第一张观测表；链上只有指导书时返回 None。"""
        for node in self.source_briefs(answer_id):
            if node in self.tables:
                return self.tables[node]
        return None

    @staticmethod
    def cn_to_int(token: str) -> int | None:
        from .conventions import CN_DIGITS

        if token.isdigit():
            return int(token)
        if token in CN_DIGITS:
            return CN_DIGITS[token]
        return None
