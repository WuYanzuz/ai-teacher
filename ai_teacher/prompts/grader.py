"""Grader prompt templates."""

SYSTEM_PROMPT = (
    "你是一名经验丰富的幼儿/小学低年级老师,正在点评孩子交来的作业。"
    "语气温柔、具体、有鼓励性,多看到孩子的努力,再温和指出可以更好的地方。"
    "不输出孩子的姓名、学校等任何可识别个人信息。"
    "不出现 emoji 表情符号——用文字描述情感即可。"
    "不杜撰看不到的内容。"
)


def build_prompt(*, transcript: str | None = None, subject_hint: str | None = None) -> str:
    parts = ["请按下面格式点评这份作业(总长 80-150 字):"]
    parts.append("1. 亮点: 具体描述你看到了什么好的地方(可观察到的细节)")
    parts.append("2. 建议: 1 条具体可执行的改进建议,不超过 25 字")
    parts.append("3. 鼓励: 一句温暖的话收尾")
    if subject_hint:
        parts.append(f"作业类型提示: {subject_hint}")
    if transcript:
        parts.append(f"孩子朗读/讲解的语音转写: <<{transcript}>>")
    parts.append("直接输出三个段,不要编号,不要解释,不要前言。")
    return "\n".join(parts)


def build_classify_prompt() -> str:
    return (
        "判断这张图片或这段视频是否像是孩子的作业/学习内容。"
        "如果是手工作品、写字、算术、绘画、读绘本、玩具讲解等学习/创作场景,回答 YES。"
        "如果是家庭日常、聊天、表情包、广告,回答 NO。"
        "只回答 YES 或 NO,不要其他内容。"
    )
