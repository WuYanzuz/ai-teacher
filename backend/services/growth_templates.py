"""Default quick-record dimensions/options + idempotent seeding."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GrowthTemplate, GrowthTemplateOption

# code, label, [options] — shown in this order on the checkin page.
DEFAULT_TEMPLATES: list[tuple[str, str, list[str]]] = [
    ("meal", "吃饭", ["吃光啦", "饭量不错", "有点挑食", "需要喂饭"]),
    ("nap", "午睡", ["自己入睡", "哄睡后入睡", "睡了一会儿", "没睡"]),
    ("mood", "情绪", ["开心", "平稳", "哭闹", "粘人"]),
    ("water", "喝水", ["主动喝水", "喝水正常", "喝水偏少"]),
    ("toilet", "如厕", ["自己如厕", "提醒后如厕", "尿湿裤子"]),
    ("activity", "活动", ["户外活动", "手工画画", "游戏", "阅读"]),
]


def seed_default_templates(db: Session) -> None:
    """Create system templates (classroom_id IS NULL) once. Idempotent."""
    existing = db.scalar(select(GrowthTemplate.id).where(GrowthTemplate.classroom_id.is_(None)))
    if existing:
        return
    for sort_order, (code, label, options) in enumerate(DEFAULT_TEMPLATES, start=1):
        tpl = GrowthTemplate(
            classroom_id=None,
            code=code,
            label=label,
            multi_select=1,
            sort_order=sort_order,
            active=1,
        )
        db.add(tpl)
        db.flush()
        for opt_order, opt_label in enumerate(options, start=1):
            db.add(GrowthTemplateOption(
                template_id=tpl.id, label=opt_label, sort_order=opt_order,
            ))
    db.commit()
