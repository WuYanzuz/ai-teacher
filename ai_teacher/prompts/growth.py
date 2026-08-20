"""Prompt for child growth reports."""


def build_report_prompt(child_name: str, history: list[dict]) -> str:
    """Build a prompt that asks the LLM to summarize a child's growth trend.

    history: list of {"date": str, "type": str, "feedback": str, "metric": float}
    """
    if not history:
        return f"孩子 {child_name} 暂无历史作业,无需生成报告。"

    lines = [f"孩子: {child_name}", f"历史作业数: {len(history)}", "", "历史记录:"]
    for h in history[-10:]:  # cap to last 10
        lines.append(
            f"- {h.get('date', '?')} | {h.get('type', '?')} | "
            f"评分 {h.get('metric', '?')}/5 | {h.get('feedback', '')}"
        )
    lines.append("")
    lines.append("请生成一段 100-200 字的成长小结,包含:")
    lines.append("1. 整体趋势(进步/稳定/波动)")
    lines.append("2. 主要亮点(具体)")
    lines.append("3. 需要关注的方向(1-2 条)")
    lines.append("直接输出三个自然段,不要编号,不要前言。")
    return "\n".join(lines)
