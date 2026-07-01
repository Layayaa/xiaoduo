#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Customer auto-reply evaluation pipeline.

Important design choice:
  - Scoring uses only user_question + auto_reply + rubric.
  - human_ref.json is used only after scoring for validation/calibration.

This avoids leaking the human reference answer into the automatic evaluator.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


QUESTION_FIELDS = ("user_question", "question", "query", "input", "customer_question")
REPLY_FIELDS = ("auto_reply", "reply", "answer", "response", "auto_response")
ID_FIELDS = ("id", "case_id", "qid", "ticket_id")
REF_FIELDS = ("human_reference", "human_reply", "reference_reply", "reference", "gold_reply")
NOTE_FIELDS = ("annotator_notes", "analysis", "annotation", "human_analysis", "notes")


@dataclass
class AutoCase:
    case_id: str
    user_question: str
    auto_reply: str


@dataclass
class HumanRef:
    case_id: str
    human_reference: str
    annotator_notes: str


RUBRIC = {
    "problem_fit": {
        "name": "问题匹配度",
        "business_term": "准确",
        "why": "判断回复是否回应当前用户的真实诉求，而不是只给泛泛说明。",
    },
    "resolution_helpfulness": {
        "name": "解决有用性",
        "business_term": "有用",
        "why": "客服回复要推动问题解决，需要明确下一步、主动代办或追问关键信息。",
    },
    "context_awareness": {
        "name": "上下文核实意识",
        "business_term": "不能瞎编",
        "why": "缺少订单、账号、商品、物流等上下文时，应该追问或说明需核实，而不是给确定结论。",
    },
    "tone_empathy": {
        "name": "语气与安抚",
        "business_term": "语气好",
        "why": "投诉、故障、等待、账号安全等场景需要先处理用户情绪。",
    },
    "automation_readiness": {
        "name": "自动化可放行度",
        "business_term": "是否扩大覆盖",
        "why": "最终要回答这条回复能否自动发出，还是必须人工兜底。",
    },
}

WEIGHTS = {
    "problem_fit": 0.25,
    "resolution_helpfulness": 0.25,
    "context_awareness": 0.20,
    "tone_empathy": 0.15,
    "automation_readiness": 0.15,
}

EMPATHY_TERMS = ("抱歉", "不好意思", "理解", "感谢", "久等", "困扰", "不便", "请放心")
ACTION_TERMS = ("请", "提供", "订单号", "账号", "截图", "确认", "申请", "提交", "修改密码", "开启二次验证", "取消", "换新", "退货退款")
PROACTIVE_TERMS = ("我帮您", "我来帮", "直接帮您", "帮您查", "帮您处理", "帮您确认", "帮您联系", "协助您", "记录下来")
SELF_SERVICE_PATTERNS = (
    r"您可以尝试",
    r"建议您尝试",
    r"尝试以下操作",
    r"建议您.{0,12}查看",
    r"您可以在订单详情页",
    r"查看商品详情页",
    r"查看订单详情",
    r"查看物流",
    r"请联系客服",
    r"联系快递公司",
    r"联系快递员",
    r"咨询具体航空公司",
    r"参考.{0,8}政策",
    r"耐心等待",
    r"按照退货地址",
    r"流程一般包括",
    r"到.{0,8}去取",
    r"自己",
)
RISKY_PATTERNS = (
    r"保证",
    r"绝对",
    r"一定(?:会|能)",
    r"马上到账",
    r"无需核实",
    r"不用验证",
    r"密码发给",
    r"身份证.*发给",
    r"银行卡.*发给",
)

CONTEXT_NEEDS = {
    "order_lookup": {
        "question_patterns": (r"退款", r"取消", r"退货", r"换.{0,3}尺码", r"买.{0,6}三天", r"用了两周", r"坏", r"没声音"),
        "expected_reply_patterns": (r"订单号", r"我帮您查", r"我帮您处理", r"申请", r"换新", r"退货退款", r"质保"),
        "label": "需要订单/售后状态核实",
    },
    "logistics_lookup": {
        "question_patterns": (r"快递", r"物流", r"补货", r"到了", r"没更新", r"取不出来"),
        "expected_reply_patterns": (r"订单号", r"物流", r"我帮您查", r"帮您联系", r"快递公司", r"提醒"),
        "label": "需要物流/库存状态核实",
    },
    "account_security": {
        "question_patterns": (r"账号", r"异地登录", r"短信"),
        "expected_reply_patterns": (r"不要点击", r"登录记录", r"修改密码", r"二次验证", r"冻结", r"账号"),
        "label": "需要账号安全核实",
    },
    "product_attribute": {
        "question_patterns": (r"这个", r"这款", r"材质", r"成分", r"手机壳", r"充电宝", r"面膜", r"哪.{0,3}好", r"包"),
        "expected_reply_patterns": (r"这款", r"额定", r"材质", r"成分", r"参数", r"哪款", r"预算", r"使用场景"),
        "label": "需要商品参数/具体商品核实",
    },
    "complaint": {
        "question_patterns": (r"态度太差", r"没人理", r"又是坏", r"太复杂", r"搞半天", r"不工作"),
        "expected_reply_patterns": (r"直接帮您", r"我帮您", r"补偿", r"卡在哪", r"一步步", r"不用再等", r"原来的问题", r"倾向哪种"),
        "label": "需要投诉安抚和人工兜底",
    },
}

ISSUE_TYPES = {
    "generic_answer": {
        "auto_patterns": (r"泛泛|通用|罗列|可能有以下原因|一般情况下|规则如下",),
        "human_patterns": (r"泛泛|通用|罗列|一堆可能原因|规则说明",),
        "label": "泛泛回复",
    },
    "no_lookup": {
        "auto_patterns": (r"订单号|账号|哪款|哪两款|具体|卡在哪",),
        "human_patterns": (r"没有帮.*查|没有查|实际查询|查一下|查用户|查具体|没有帮用户实际排查",),
        "label": "缺少查询/核实",
    },
    "push_to_user": {
        "auto_patterns": SELF_SERVICE_PATTERNS,
        "human_patterns": (r"推给了用户|让用户自己|把用户推走|自己去|操作负担|用户不关心|不想自己|没用",),
        "label": "把责任推给用户",
    },
    "missing_clarification": {
        "auto_patterns": (r"订单号|账号|哪款|哪两款|具体|预算|使用场景|卡在哪|倾向哪种",),
        "human_patterns": (r"需要确认|追问|请问|告诉我|哪两款|哪款|订单号|账号|卡在哪|倾向哪种",),
        "label": "缺少必要追问",
    },
    "weak_empathy": {
        "auto_patterns": EMPATHY_TERMS,
        "human_patterns": (r"情绪|生气|害怕|不满|安抚|重视|特殊安抚|语气",),
        "label": "安抚不足",
    },
    "acceptable": {
        "auto_patterns": (),
        "human_patterns": (r"基本正确|处理得不错|质量尚可|可接受|有价值",),
        "label": "人工认为基本可接受",
    },
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def as_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "cases", "data", "records", "examples"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("JSON must be a list or a dict containing items/cases/data/records/examples.")


def first_value(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = row.get(field)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    return ""


def load_auto_cases(path: Path) -> list[AutoCase]:
    cases: list[AutoCase] = []
    for index, row in enumerate(as_items(load_json(path)), start=1):
        case_id = first_value(row, ID_FIELDS) or str(index)
        question = first_value(row, QUESTION_FIELDS).strip()
        reply = first_value(row, REPLY_FIELDS).strip()
        if not question or not reply:
            raise ValueError(f"Case {case_id} is missing user_question or auto_reply.")
        cases.append(AutoCase(case_id=case_id, user_question=question, auto_reply=reply))
    return cases


def load_human_refs(path: Path) -> dict[str, HumanRef]:
    refs: dict[str, HumanRef] = {}
    for index, row in enumerate(as_items(load_json(path)), start=1):
        case_id = first_value(row, ID_FIELDS) or str(index)
        refs[case_id] = HumanRef(
            case_id=case_id,
            human_reference=first_value(row, REF_FIELDS).strip(),
            annotator_notes=first_value(row, NOTE_FIELDS).strip(),
        )
    return refs


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def count_patterns(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))


def clamp_score(score: float) -> int:
    return int(max(1, min(5, round(score))))


def score_to_100(score_1_to_5: int) -> int:
    return int(round(score_1_to_5 * 20))


def detect_context_needs(question: str) -> list[dict[str, Any]]:
    needs = []
    for key, spec in CONTEXT_NEEDS.items():
        if has_any(question, spec["question_patterns"]):
            needs.append({"key": key, **spec})
    return needs


def covered_need(reply: str, need: dict[str, Any]) -> bool:
    return has_any(reply, need["expected_reply_patterns"])


def detect_auto_issues(question: str, reply: str) -> list[str]:
    needs = detect_context_needs(question)
    issues: list[str] = []
    self_service_hits = count_patterns(reply, SELF_SERVICE_PATTERNS)
    proactive_hits = count_terms(reply, PROACTIVE_TERMS)
    risky_hits = count_patterns(reply, RISKY_PATTERNS)
    generic_hits = count_patterns(reply, (r"可能有以下原因", r"一般情况下", r"规则如下", r"建议您.*查看", r"如有疑问"))
    asks_key_info = has_any(reply, (r"订单号", r"账号", r"哪款", r"哪两款", r"具体", r"预算", r"使用场景", r"卡在哪", r"倾向哪种"))

    uncovered = [need for need in needs if not covered_need(reply, need)]
    if generic_hits >= 1:
        issues.append("generic_answer")
    if uncovered:
        issues.append("no_lookup")
    if self_service_hits > proactive_hits:
        issues.append("push_to_user")
    if any(need["key"] in {"product_attribute", "order_lookup", "logistics_lookup"} for need in uncovered):
        issues.append("missing_clarification")
    if any(need["key"] in {"complaint", "account_security"} for need in needs) and count_terms(reply, EMPATHY_TERMS) == 0:
        issues.append("weak_empathy")
    if any(need["key"] == "complaint" for need in needs) and not asks_key_info:
        issues.append("missing_clarification")
    if risky_hits:
        issues.append("hallucination_risk")
    return sorted(set(issues))


def score_case(case: AutoCase) -> dict[str, Any]:
    question = case.user_question
    reply = case.auto_reply
    needs = detect_context_needs(question)
    covered = [need for need in needs if covered_need(reply, need)]
    uncovered = [need for need in needs if not covered_need(reply, need)]
    has_complaint_need = any(need["key"] == "complaint" for need in needs)
    has_product_need = any(need["key"] == "product_attribute" for need in needs)
    has_order_or_logistics_need = any(need["key"] in {"order_lookup", "logistics_lookup"} for need in needs)

    empathy_hits = count_terms(reply, EMPATHY_TERMS)
    action_hits = count_terms(reply, ACTION_TERMS)
    proactive_hits = count_terms(reply, PROACTIVE_TERMS)
    self_service_hits = count_patterns(reply, SELF_SERVICE_PATTERNS)
    risky_hits = count_patterns(reply, RISKY_PATTERNS)
    generic_hits = count_patterns(reply, (r"可能有以下原因", r"一般情况下", r"规则如下", r"建议您.*查看", r"如有疑问"))
    asks_key_info = has_any(reply, (r"订单号", r"账号", r"哪款", r"哪两款", r"具体", r"预算", r"使用场景", r"卡在哪", r"倾向哪种"))

    problem_fit = 3.2
    if not needs:
        problem_fit += 0.3
    problem_fit += min(len(covered), 2) * 0.6
    problem_fit -= min(len(uncovered), 2) * 0.9
    problem_fit -= min(generic_hits, 2) * 0.4
    if has_complaint_need and not asks_key_info and proactive_hits == 0:
        problem_fit -= 0.8
    if has_product_need and self_service_hits and not asks_key_info:
        problem_fit -= 0.5

    resolution_helpfulness = 2.4 + min(action_hits, 4) * 0.25 + min(proactive_hits, 2) * 0.8
    if asks_key_info:
        resolution_helpfulness += 0.4
    resolution_helpfulness -= min(self_service_hits, 3) * 0.55
    resolution_helpfulness -= min(len(uncovered), 2) * 0.5
    if has_complaint_need and proactive_hits == 0:
        resolution_helpfulness -= 0.9
    if has_order_or_logistics_need and generic_hits and not asks_key_info:
        resolution_helpfulness -= 0.6

    context_awareness = 3.4
    if needs and (covered or asks_key_info):
        context_awareness += 0.9
    if needs and not covered and not asks_key_info:
        context_awareness -= 1.2
    context_awareness -= risky_hits * 1.4
    context_awareness -= max(0, generic_hits - 1) * 0.3
    if has_complaint_need and not asks_key_info:
        context_awareness -= 0.5

    tone_empathy = 3.0 + min(empathy_hits, 3) * 0.55 + min(proactive_hits, 2) * 0.3
    if any(need["key"] in {"complaint", "account_security"} for need in needs) and empathy_hits == 0:
        tone_empathy -= 0.9
    tone_empathy -= min(self_service_hits, 2) * 0.25
    if has_complaint_need and proactive_hits == 0:
        tone_empathy -= 0.4

    automation_readiness = 3.1
    automation_readiness += min(len(covered), 2) * 0.4 + min(proactive_hits, 2) * 0.35
    automation_readiness -= min(len(uncovered), 2) * 0.75
    automation_readiness -= min(self_service_hits, 3) * 0.35
    automation_readiness -= risky_hits * 1.5
    if any(need["key"] == "complaint" for need in needs):
        automation_readiness -= 0.8
    if has_complaint_need and not asks_key_info and proactive_hits == 0:
        automation_readiness -= 0.8

    scores_1_to_5 = {
        "problem_fit": clamp_score(problem_fit),
        "resolution_helpfulness": clamp_score(resolution_helpfulness),
        "context_awareness": clamp_score(context_awareness),
        "tone_empathy": clamp_score(tone_empathy),
        "automation_readiness": clamp_score(automation_readiness),
    }
    weighted = sum(score_to_100(scores_1_to_5[name]) * weight for name, weight in WEIGHTS.items())
    overall = int(round(weighted))

    issues = detect_auto_issues(question, reply)
    if overall >= 80 and not issues:
        decision = "pass"
    elif overall >= 65 and "hallucination_risk" not in issues:
        decision = "needs_review"
    else:
        decision = "fail"

    reasons = []
    if uncovered:
        reasons.append("需要核实的信息未覆盖：" + "、".join(need["label"] for need in uncovered))
    if self_service_hits > proactive_hits:
        reasons.append("回复偏自助说明，把操作负担留给用户")
    if generic_hits:
        reasons.append("回复偏通用解释，缺少针对当前 case 的判断")
    if risky_hits:
        reasons.append("存在过度承诺或安全合规风险")
    if not reasons:
        reasons.append("核心诉求、下一步和风险边界基本覆盖")

    return {
        "case_id": case.case_id,
        "user_question": question,
        "auto_reply": reply,
        "scores_1_to_5": scores_1_to_5,
        "scores": {name: score_to_100(score) for name, score in scores_1_to_5.items()},
        "overall": overall,
        "decision": decision,
        "auto_issue_types": issues,
        "detected_context_needs": [need["label"] for need in needs],
        "signals": {
            "empathy_hits": empathy_hits,
            "action_hits": action_hits,
            "proactive_hits": proactive_hits,
            "self_service_hits": self_service_hits,
            "risky_hits": risky_hits,
            "generic_hits": generic_hits,
            "asks_key_info": asks_key_info,
            "covered_context_needs": [need["label"] for need in covered],
            "uncovered_context_needs": [need["label"] for need in uncovered],
        },
        "judge_reason": "；".join(reasons),
    }


def detect_human_issue_types(ref: HumanRef) -> list[str]:
    text = ref.human_reference + "\n" + ref.annotator_notes
    issues = []
    for issue_key, spec in ISSUE_TYPES.items():
        if issue_key == "acceptable":
            continue
        if has_any(text, spec["human_patterns"]):
            issues.append(issue_key)
    return sorted(set(issues))


def validate_against_human(results: list[dict[str, Any]], refs: dict[str, HumanRef]) -> dict[str, Any]:
    rows = []
    issue_hits = Counter()
    issue_total = Counter()
    matched_cases = 0
    auto_low_cases = {row["case_id"] for row in sorted(results, key=lambda item: item["overall"])[:5]}
    human_negative_cases = set()

    for row in results:
        ref = refs.get(row["case_id"])
        if not ref:
            continue
        human_issues = detect_human_issue_types(ref)
        auto_issues = set(row["auto_issue_types"])
        matched = sorted(auto_issues.intersection(human_issues))
        missed = sorted(set(human_issues) - auto_issues)
        extra = sorted(auto_issues - set(human_issues))
        if human_issues:
            human_negative_cases.add(row["case_id"])
        if matched:
            matched_cases += 1
        for issue in human_issues:
            issue_total[issue] += 1
            if issue in auto_issues:
                issue_hits[issue] += 1
        rows.append(
            {
                "case_id": row["case_id"],
                "overall": row["overall"],
                "decision": row["decision"],
                "auto_issue_types": sorted(auto_issues),
                "human_issue_types": human_issues,
                "matched_issue_types": matched,
                "missed_human_issue_types": missed,
                "extra_auto_issue_types": extra,
                "human_reference": ref.human_reference,
                "annotator_notes": ref.annotator_notes,
            }
        )

    total_human_issue_mentions = sum(issue_total.values())
    total_hits = sum(issue_hits.values())
    issue_recall = round(total_hits / total_human_issue_mentions, 3) if total_human_issue_mentions else None
    top5_overlap = sorted(auto_low_cases.intersection(human_negative_cases))
    return {
        "case_count": len(rows),
        "matched_case_count": matched_cases,
        "matched_case_rate": round(matched_cases / len(rows), 3) if rows else None,
        "human_issue_recall": issue_recall,
        "issue_hits": dict(issue_hits),
        "issue_totals": dict(issue_total),
        "auto_lowest_5_cases": sorted(auto_low_cases),
        "human_negative_cases": sorted(human_negative_cases),
        "top5_overlap_with_human_negative": top5_overlap,
        "rows": rows,
    }


def bucket(score: int) -> str:
    if score >= 80:
        return "80-100 可自动放行"
    if score >= 65:
        return "65-79 需抽检优化"
    return "<65 人工兜底"


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = list(WEIGHTS.keys()) + ["overall"]
    summary: dict[str, Any] = {"count": len(results), "metrics": {}, "decisions": dict(Counter(row["decision"] for row in results))}
    for metric in metrics:
        if metric == "overall":
            values = [row["overall"] for row in results]
        else:
            values = [row["scores"][metric] for row in results]
        summary["metrics"][metric] = {
            "avg": round(sum(values) / len(values), 1),
            "min": min(values),
            "max": max(values),
            "distribution": dict(Counter(bucket(value) for value in values)),
        }
    issue_counter = Counter(issue for row in results for issue in row["auto_issue_types"])
    summary["issue_distribution"] = dict(issue_counter)
    return summary


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        clean = [str(cell).replace("\n", "<br>").replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(clean) + " |")
    return "\n".join(lines)


def render_markdown(results: list[dict[str, Any]], summary: dict[str, Any], validation: dict[str, Any], criteria: str) -> str:
    worst = sorted(results, key=lambda row: row["overall"])[:3]
    metric_rows = [
        [
            metric,
            data["avg"],
            data["min"],
            data["max"],
            ", ".join(f"{name}: {count}" for name, count in data["distribution"].items()),
        ]
        for metric, data in summary["metrics"].items()
    ]
    case_rows = [
        [
            row["case_id"],
            row["overall"],
            row["decision"],
            row["scores"]["problem_fit"],
            row["scores"]["resolution_helpfulness"],
            row["scores"]["context_awareness"],
            row["scores"]["tone_empathy"],
            row["scores"]["automation_readiness"],
            "、".join(row["auto_issue_types"]) or "none",
        ]
        for row in results
    ]
    worst_blocks = []
    validation_by_id = {row["case_id"]: row for row in validation["rows"]}
    for row in worst:
        val = validation_by_id.get(row["case_id"], {})
        worst_blocks.append(
            "\n".join(
                [
                    f"### {row['case_id']} | overall={row['overall']} | {row['decision']}",
                    "",
                    f"- 用户问题：{row['user_question']}",
                    f"- 自动回复：{row['auto_reply']}",
                    f"- 自动评估原因：{row['judge_reason']}",
                    f"- 自动识别问题：{'、'.join(row['auto_issue_types']) or 'none'}",
                    f"- 人工标注问题类型（仅验证用）：{'、'.join(val.get('human_issue_types', [])) or 'none'}",
                    f"- 人工分析（仅验证用）：{val.get('annotator_notes', '')}",
                ]
            )
        )

    validation_rows = [
        [
            row["case_id"],
            row["overall"],
            "、".join(row["auto_issue_types"]) or "none",
            "、".join(row["human_issue_types"]) or "none",
            "、".join(row["matched_issue_types"]) or "none",
            "、".join(row["missed_human_issue_types"]) or "none",
        ]
        for row in validation["rows"]
    ]

    return "\n\n".join(
        [
            "# 客服自动回复质量评估报告",
            "## 1. 方法边界",
            "- 评分阶段只使用 `user_question` 和 `auto_reply`，不读取人工参考答案。",
            "- `human_ref.json` 只在评分完成后用于 validation，检查自动评估发现的问题是否接近人工标注。",
            "- 默认模式是离线 mock judge，适合复现；线上可替换为 LLM-as-judge，但仍应保持同样的数据隔离。",
            "## 2. 整体结论",
            f"- 样本数：{summary['count']} 条",
            f"- 整体平均分：{summary['metrics']['overall']['avg']} / 100",
            f"- 最低/最高分：{summary['metrics']['overall']['min']} / {summary['metrics']['overall']['max']}",
            f"- 放行决策分布：{json.dumps(summary['decisions'], ensure_ascii=False)}",
            "- 判断：当前自动回复可覆盖部分规则清晰的低风险问题，但凡涉及订单、物流、商品参数、投诉情绪和账号安全，都应保留人工兜底或强制追问。",
            "## 3. 指标分布",
            md_table(["metric", "avg", "min", "max", "distribution"], metric_rows),
            "## 4. 逐条评分",
            md_table(
                [
                    "case_id",
                    "overall",
                    "decision",
                    "problem_fit",
                    "resolution_helpfulness",
                    "context_awareness",
                    "tone_empathy",
                    "automation_readiness",
                    "auto_issue_types",
                ],
                case_rows,
            ),
            "## 5. 最差 3 条 case",
            "\n\n".join(worst_blocks),
            "## 6. 使用 human_ref 的验证结果",
            f"- case 级命中率：{validation['matched_case_rate']}（自动评估识别到至少一个人工问题类型的比例）",
            f"- 人工问题类型召回率：{validation['human_issue_recall']}",
            f"- 自动最低 5 条与人工负面 case 重合：{', '.join(validation['top5_overlap_with_human_negative']) or 'none'}",
            md_table(["case_id", "overall", "auto issues", "human issues", "matched", "missed"], validation_rows),
            "## 7. 业务要求原文",
            criteria.strip(),
        ]
    )


def render_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    lines = escaped.splitlines()
    rendered: list[str] = []
    in_table = False
    for line in lines:
        if line.startswith("| "):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if set(cells) == {"---"}:
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                rendered.append("<table>")
                in_table = True
            rendered.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue
        if in_table:
            rendered.append("</table>")
            in_table = False
        if line.startswith("# "):
            rendered.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            rendered.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            rendered.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("- "):
            rendered.append(f"<p class=\"bullet\">{line}</p>")
        elif line:
            rendered.append(f"<p>{line}</p>")
    if in_table:
        rendered.append("</table>")
    body = "\n".join(rendered)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>客服自动回复质量评估报告</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      color: #1f2937;
      margin: 32px auto;
      max-width: 1240px;
      line-height: 1.62;
      background: #f8fafc;
    }}
    h1, h2, h3 {{ color: #111827; line-height: 1.25; }}
    h1 {{ font-size: 30px; }}
    h2 {{ margin-top: 32px; border-bottom: 1px solid #d1d5db; padding-bottom: 8px; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 16px 0 24px;
      background: #ffffff;
      font-size: 13px;
    }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 9px; vertical-align: top; }}
    th {{ background: #e5e7eb; text-align: left; }}
    p {{ background: #ffffff; margin: 0 0 8px; padding: 8px 10px; }}
    .bullet {{ border-left: 3px solid #2563eb; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def write_outputs(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    validation: dict[str, Any],
    criteria: str,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = render_markdown(results, summary, validation, criteria)
    (output_dir / "evaluation_report.md").write_text(report, encoding="utf-8")
    (output_dir / "evaluation_report.html").write_text(render_html(report), encoding="utf-8")
    (output_dir / "evaluation_results.json").write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "validation_summary.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "case_scores.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case_id",
                "overall",
                "decision",
                "problem_fit",
                "resolution_helpfulness",
                "context_awareness",
                "tone_empathy",
                "automation_readiness",
                "auto_issue_types",
            ]
        )
        for row in results:
            writer.writerow(
                [
                    row["case_id"],
                    row["overall"],
                    row["decision"],
                    row["scores"]["problem_fit"],
                    row["scores"]["resolution_helpfulness"],
                    row["scores"]["context_awareness"],
                    row["scores"]["tone_empathy"],
                    row["scores"]["automation_readiness"],
                    "、".join(row["auto_issue_types"]),
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate customer-service auto replies.")
    parser.add_argument("--auto", default="task3_auto_replies.json", help="Path to auto replies JSON.")
    parser.add_argument("--ref", default="task3_human_ref.json", help="Path to human reference JSON, validation only.")
    parser.add_argument("--criteria", default="task3_eval_criteria.md", help="Path to business criteria markdown.")
    parser.add_argument("--out", default="outputs", help="Output directory.")
    parser.add_argument("--mode", choices=("mock",), default="mock", help="mock = offline deterministic judge.")
    args = parser.parse_args()

    auto_path = Path(args.auto)
    ref_path = Path(args.ref)
    criteria_path = Path(args.criteria)
    missing = [str(path) for path in (auto_path, criteria_path) if not path.exists()]
    if missing:
        print("Missing required scoring input file(s): " + ", ".join(missing))
        return 2
    if not ref_path.exists():
        print("Missing validation file: " + str(ref_path))
        return 2

    cases = load_auto_cases(auto_path)
    results = [score_case(case) for case in cases]
    summary = summarize(results)
    refs = load_human_refs(ref_path)
    validation = validate_against_human(results, refs)
    criteria = criteria_path.read_text(encoding="utf-8")
    write_outputs(results, summary, validation, criteria, Path(args.out))

    print(f"Evaluated {len(results)} cases without using human_ref for scoring.")
    print(f"Overall average: {summary['metrics']['overall']['avg']} / 100")
    print(f"Decision distribution: {json.dumps(summary['decisions'], ensure_ascii=False)}")
    print(f"Validation issue recall: {validation['human_issue_recall']}")
    print(f"Lowest cases: {', '.join(row['case_id'] for row in sorted(results, key=lambda x: x['overall'])[:3])}")
    print(f"Report: {Path(args.out) / 'evaluation_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
