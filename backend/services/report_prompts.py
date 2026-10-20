"""Prompt construction for per-child daily/weekly reports.

Pure functions (no DB, no FastAPI) so they are easy to unit-test.
"""

from __future__ import annotations

from datetime import date, timedelta

# Fallback labels if the template table is unavailable; keep in sync with
# services/growth_templates.py DEFAULT_TEMPLATES.
CATEGORY_LABELS = {
    "meal": "吃饭",
    "nap": "午睡",
    "mood": "情绪",
    "water": "喝水",
    "toilet": "如厕",
    "activity": "活动",
}

MAX_FEEDBACKS = 10
FEEDBACK_CLIP = 300

SYSTEM_PROMPT = (
    "你是一名有爱心、经验丰富的幼儿园老师,正在给家长写孩子的在园成长反馈。"
    "铁律:\n"
    "1. 只允许基于下面给出的真实记录写作,没有记录的方面一律不写,严禁编造具体事件;\n"
    "2. 不出现孩子真实姓名、学校名、其他幼儿姓名,统一用'宝贝'称呼;\n"
    "3. 不做任何医疗或心理诊断,只描述行为和状态;\n"
    "4. 鼓励要具体、语气温和,可以用 emoji,但全文不超过 5 个;\n"
    "5. 直接输出正文,不要标题、称呼、落款、前言和解释。"
)


def period_range(report_type: str, anchor: date) -> tuple[date, date]:
    """Normalize an anchor date to the reporting period.

    day  -> (anchor, anchor)
    week -> Monday .. Sunday containing the anchor
    """
    if report_type == "week":
        start = anchor - timedelta(days=anchor.weekday())  # Monday
        return start, start + timedelta(days=6)
    return anchor, anchor


def build_user_prompt(
    report_type: str,
    period_start: date,
    period_end: date,
    checkins: list[dict],
    feedbacks: list[dict],
) -> str:
    """Assemble the user message from gathered facts.

    checkins:  [{"date": date, "note": str|None,
                 "items": [{"category_code","category_label","options":[..],"note"}]}]
    feedbacks: [{"date": date, "feedback": str}]
    """
    span = (
        f"{period_start.isoformat()}（{period_start.month}月{period_start.day}日）"
        if report_type == "day"
        else f"{period_start.isoformat()} 至 {period_end.isoformat()}（本周）"
    )
    lines = [f"报告类型: {'日报' if report_type == 'day' else '周报'}", f"周期: {span}", ""]

    lines.append("【在园日常打卡记录】")
    if not checkins:
        lines.append("（本周期没有日常打卡记录,不要编造生活照料相关内容）")
    else:
        if report_type == "week":
            lines.append(f"本周共打卡 {len(checkins)} 天。")
        for day in checkins:
            parts = [f"- {day['date'].isoformat()}"]
            for it in day["items"]:
                label = it.get("category_label") or CATEGORY_LABELS.get(it["category_code"], it["category_code"])
                detail = "、".join(it["options"]) if it["options"] else ""
                if it.get("note"):
                    detail = f"{detail}({it['note']})" if detail else it["note"]
                if detail:
                    parts.append(f"{label}: {detail}")
            if day.get("note"):
                parts.append(f"老师备注: {day['note']}")
            lines.append(" | ".join(parts))
    lines.append("")

    lines.append("【作业/学习点评记录】")
    if not feedbacks:
        lines.append("（本周期没有作业点评记录,不要编造学习表现）")
    else:
        for fb in feedbacks:
            text = fb["feedback"][:FEEDBACK_CLIP]
            lines.append(f"- {fb['date'].isoformat()}: {text}")
    lines.append("")

    if report_type == "day":
        lines.append(
            "请写一篇 150-250 字的日报,按'生活照料 / 情绪社交 / 学习活动 / 给家长的一句话'组织, "
            "自然段衔接自然、不要分点编号。如果记录很少,就如实简短说明今天记录较少,并给一句通用鼓励,不要凑字数。"
        )
    else:
        lines.append(
            "请写一篇 400-600 字的周报:先按吃饭、午睡、情绪、活动等维度小结本周整体状态和变化趋势"
            "（可以引用具体事实,但连续多天相同的选项只概括一次）,再给家长 2-3 条可操作的家庭配合建议。"
            "自然段衔接自然、不要分点编号。本周记录的天数较少时如实说明,不要编造。"
        )
    return "\n".join(lines)
