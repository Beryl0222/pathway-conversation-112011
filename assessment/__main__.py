"""命令行：查看归类、证据、算值、签定、补交、澄清影响、反馈与阶段汇入。

用法示例（在仓库根目录，建议用 -I 隔离环境运行）：

    python3 -I -m assessment feedback S1
    python3 -I -m assessment scoring
    python3 -I -m assessment stage
"""
import argparse
import json

from .repository import Repository
from .fragments import classify_answer
from .evidence import supports_for_student, review_queue
from .scoring import check_calculations, first_error_map, carried_error_answers
from .judgments import evaluate_student
from .resubmission import review_resubmissions
from .rubrics import REGISTERED_CLARIFICATIONS, impact_scan, wording_diff
from .feedback import build_feedback
from .stage import build_stage_record, comparison_view


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=lambda o: getattr(o, "__dict__", str(o))))


def _student_arg(repo: Repository, value: str | None) -> list[str]:
    if value:
        if value not in repo.students:
            raise SystemExit(f"学生不存在：{value}")
        return [value]
    return list(repo.students)


def cmd_fragments(repo: Repository, args) -> None:
    for sid in _student_arg(repo, args.student):
        print(f"## {sid} 的分段句子归类")
        for answer in repo.answers_of(sid):
            print(f"[{answer['id']}] 分段={answer['分段']} 序次={answer['序次']} 引自={answer['引自'] or '无'}")
            for frag in classify_answer(answer, repo):
                flag = "｜待审：" + frag.review_reason if frag.needs_review else ""
                print(f"  {frag.index + 1}. （{frag.kind} / {frag.rule}）{frag.text}{flag}")
        print()


def cmd_evidence(repo: Repository, args) -> None:
    for sid in _student_arg(repo, args.student):
        print(f"## {sid} 的证据—规准支撑")
        for support in supports_for_student(repo, sid):
            mark = "［待审］" if support.needs_review else ""
            print(f"  {support.answer_id}句{support.fragment_index + 1} -> {support.rubric}"
                  f" [{support.level}]{mark} {support.reason}")
        print("待审队列：")
        for item in review_queue(repo, sid):
            print(f"  - {item.answer_id}句{item.fragment_index + 1} / {item.rubric}：{item.reason}")
        print()


def cmd_scoring(repo: Repository, args) -> None:
    print("## 算值核对")
    for sid, claims in check_calculations(repo).items():
        for claim in claims:
            print(f"  {sid} {claim.answer_id}：{claim.basis} | 算式正确={claim.arithmetic_ok}"
                  f" 与来源表一致={claim.matches_source} 期望值={claim.expected_value}{('｜' + claim.note) if claim.note else ''}")
    print("\n## 首错定位（数值错误只计此处）")
    for sid, aid in first_error_map(repo).items():
        print(f"  {sid}：首错 {aid}；跟随错误后续 {carried_error_answers(repo).get(sid, [])}")


def cmd_judgments(repo: Repository, args) -> None:
    for sid in _student_arg(repo, args.student):
        print(f"## {sid}（{repo.students[sid]['方向']}）要求签定状态")
        for rid, state in evaluate_student(repo, sid).items():
            print(f"  {rid} [{state.level}] {state.status} 签定人={state.signed_by or '—'}")
            for caveat in state.caveats:
                print(f"      提示：{caveat}")
        print()


def cmd_resubmit(repo: Repository, args) -> None:
    print("## 补交分段处理")
    for review in review_resubmissions(repo):
        print(f"  {review.student} {review.answer_id}（{review.segment} 序次{review.seq}）"
              f"输入未变={review.input_unchanged}")
        print(f"      冻结前段批语：{review.prior_decisions_frozen or '无'}")
        print(f"      处理：{review.treatment}")
        print(f"      依据：{review.rationale}")
        if review.needs_teacher:
            print("      ［转教师审原文］")


def cmd_rubric(repo: Repository, args) -> None:
    print("## 已登记的规准澄清")
    for clar in REGISTERED_CLARIFICATIONS:
        print(f"  {clar.rubric_id} -> 第{clar.new_version}版：{clar.kind_text}（{clar.basis}{clar.note}）")
        for line in wording_diff(repo, clar.rubric_id, clar.new_version - 1, clar.new_version):
            print(f"      {line}")
    print("\n## 已发回结果的复核影响")
    for item in impact_scan(repo):
        flag = "需复核" if item.re_review_required else "教研组新版签定，无需复核"
        print(f"  {item.marking_id}（{item.student} {item.rubric_ref}）：{flag}")
        print(f"      {item.reason}")


def cmd_feedback(repo: Repository, args) -> None:
    for sid in _student_arg(repo, args.student):
        print(build_feedback(repo, sid).as_text())
        print()


def cmd_stage(repo: Repository, args) -> None:
    record = build_stage_record(repo, args.stage)
    print(f"## 阶段 {record.stage} 汇入共用记录")
    print(f"  可汇入：{record.merged_students or '无'}")
    for sid, blockers in record.blocked.items():
        print(f"  阻断 {sid}：")
        for blocker in blockers:
            print(f"      - {blocker}")
    for sid, pending in record.direction_pending.items():
        print(f"  {sid} 方向附加待定（不阻断共同汇入）：{pending}")


def cmd_compare(repo: Repository, args) -> None:
    print("## 同一份作业两个方向的判断对比")
    for rid, payload in comparison_view(repo).items():
        print(f"  {rid} {payload['要求']}（{payload['层级']}，最新第{payload['最新版次']}版）")
        for item in payload["学生判断"]:
            print(f"      {item['学生']}({item['方向']})：{item['状态']} 签定人={item['签定人'] or '—'}"
                  f" 教研组待决={item['教研组待决']}")
            for note in item["权限提示"]:
                print(f"          {note}")


def main() -> None:
    parser = argparse.ArgumentParser(description="形成性评价整理工具")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in [
        ("fragments", cmd_fragments), ("evidence", cmd_evidence),
        ("scoring", cmd_scoring), ("judgments", cmd_judgments),
        ("resubmit", cmd_resubmit), ("rubric", cmd_rubric),
        ("feedback", cmd_feedback), ("stage", cmd_stage), ("compare", cmd_compare),
    ]:
        p = sub.add_parser(name)
        if name != "scoring" and name != "rubric" and name != "resubmit":
            p.add_argument("student", nargs="?", help="学生编号，缺省为全部")
        if name == "stage":
            p.add_argument("--stage", help="阶段，缺省取资料中的阶段")
        p.set_defaults(func=func)
    args = parser.parse_args()
    repo = Repository()
    args.func(repo, args)


if __name__ == "__main__":
    main()
