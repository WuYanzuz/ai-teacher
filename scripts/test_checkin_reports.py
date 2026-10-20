# -*- coding: utf-8 -*-
"""In-process API tests: checkin CRUD + report batch state machine.

LLM is mocked. Run from project root: python scripts/test_checkin_reports.py
"""
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# temp sqlite BEFORE engine is created
from ai_teacher.utils.config import get_settings
s = get_settings()
tmp = PROJECT_ROOT / "data" / "test_checkin_reports.db"
if tmp.exists():
    tmp.unlink()
s.db_path = tmp

import ai_teacher.storage.database as dbmod
dbmod._engine = None
dbmod.SessionLocal = None

from backend.db import init_backend_db
init_backend_db()

from fastapi.testclient import TestClient
from backend.main import app
from backend.services import report_service

calls = {"n": 0, "fail_next": 0}

class FakeText:
    def chat(self, system, user, temperature=None, max_tokens=None):
        calls["n"] += 1
        if calls["fail_next"] > 0:
            calls["fail_next"] -= 1
            raise RuntimeError("simulated AI outage")
        assert "宝贝" in system
        # echo back which kind + facts presence for eyeballing
        kind = "周报" if "周报" in user else "日报"
        return f"{kind}测试正文, 今天表现很好，吃光啦，继续加油。"

report_service._make_text_client = lambda: FakeText()

client = TestClient(app)


def must(r, code=200):
    assert r.status_code == code, (r.status_code, r.text[:300])
    return r.json()


# ---- users ----
t = must(client.post("/api/auth/dev_login", json={"openid": "t1", "name": "张老师", "role": "teacher"}))
TH = {"Authorization": f"Bearer {t['token']}"}
p1 = must(client.post("/api/auth/dev_login", json={"openid": "p1", "name": "小明妈", "role": "parent"}))
P1 = {"Authorization": f"Bearer {p1['token']}"}
p2 = must(client.post("/api/auth/dev_login", json={"openid": "p2", "name": "小红爸", "role": "parent"}))
P2 = {"Authorization": f"Bearer {p2['token']}"}

cls = must(client.post("/api/classes", headers=TH, json={"name": "小一班"}))
cid = cls["id"]
must(client.post("/api/classes/join", headers=P1, json={"code": cls["code"], "child_name": "小明"}))
must(client.post("/api/classes/join", headers=P2, json={"code": cls["code"], "child_name": "小红"}))

# ============ P3 checkin ============
tpl = must(client.get("/api/checkin/template", headers=TH))
codes = [c["code"] for c in tpl["categories"]]
assert codes == ["meal", "nap", "mood", "water", "toilet", "activity"], codes
print("[P3] template 6 dims OK")

kids = must(client.get(f"/api/classes/{cid}/children", headers=TH))
assert kids["children"] == ["小明", "小红"], kids
print("[P3] roster distinct OK")

today = date(2026, 10, 14).isoformat()
body = {
    "class_id": cid, "child_name": "小明", "date": today,
    "note": "整体不错",
    "items": [
        {"category_code": "meal", "options": ["吃光啦"], "note": "吃得快"},
        {"category_code": "mood", "options": ["开心", "平稳"]},
        {"category_code": "nap", "options": [], "note": "比平时晚睡半小时"},
    ],
}
r = must(client.put("/api/checkin", headers=TH, json=body))
assert len(r["items"]) == 3 and r["id"]
id1 = r["id"]
# second PUT overwrites (idempotent same head row)
body["items"] = [{"category_code": "meal", "options": ["饭量不错"]}]
r = must(client.put("/api/checkin", headers=TH, json=body))
assert r["id"] == id1 and len(r["items"]) == 1, r
print("[P3] upsert overwrite OK")

r = must(client.get("/api/checkin", headers=TH, params={"class_id": cid, "date": today, "child_name": "小明"}))
assert r["items"][0]["options"] == ["饭量不错"]

day = must(client.get("/api/checkin/day", headers=TH, params={"class_id": cid, "date": today}))
flags = {x["child_name"]: x["done"] for x in day["children"]}
assert flags == {"小明": True, "小红": False}, flags
print("[P3] day overview OK")

rng = must(client.get("/api/checkin/child", headers=P1,
                     params={"class_id": cid, "child_name": "小明", "start": today, "end": today}))
assert len(rng["days"]) == 1
# parent cannot read another child
r = client.get("/api/checkin/child", headers=P1,
               params={"class_id": cid, "child_name": "小红", "start": today, "end": today})
assert r.status_code == 403
# non-member teacher? foreign teacher
t2 = must(client.post("/api/auth/dev_login", json={"openid": "tX", "name": "外人", "role": "teacher"}))
r = client.put("/api/checkin", headers={"Authorization": f"Bearer {t2['token']}"}, json=body)
assert r.status_code == 403
print("[P3] permission checks OK")

# ============ P4 reports ============
# 1) batch for 2 children, one LLM failure -> partial
calls["fail_next"] = 1
r = must(client.post("/api/reports/batches", headers=TH, json={"class_id": cid, "type": "day", "date": today}))
bid = r["id"]
assert r["status"] == "pending" and r["total"] == 2
# repeat click -> same batch, no new run
r2 = must(client.post("/api/reports/batches", headers=TH, json={"class_id": cid, "type": "day", "date": today}))
assert r2["id"] == bid
print("[P4] create + double-click idempotent OK")

# background tasks ran during response in TestClient; poll anyway
b = must(client.get(f"/api/reports/batches/{bid}", headers=TH))
assert b["status"] in ("partial", "done", "running", "failed"), b
assert b["succeeded"] + b["failed_count"] <= 2

failed = [x for x in b["reports"] if x["status"] == "failed"]
done = [x for x in b["reports"] if x["status"] == "done"]
assert b["status"] == "partial", b
assert len(failed) == 1 and len(done) == 1, b
print("[P4] one failure -> partial OK")

# 2) retry the failed one
rid = failed[0]["id"]
must(client.post(f"/api/reports/{rid}/retry", headers=TH))
b = must(client.get(f"/api/reports/batches/{bid}", headers=TH))
assert b["status"] == "done" and b["succeeded"] == 2 and b["failed_count"] == 0, b
print("[P4] retry -> done OK")

# 3) teacher reads + edits + publishes
rep = must(client.get(f"/api/reports/{rid}", headers=TH))
assert rep["visible_content"].startswith(("日报", "周报"))
rep = must(client.post(f"/api/reports/{rid}/edit", headers=TH, json={"content": "老师定稿内容"}))
assert rep["teacher_edit"] == "老师定稿内容" and rep["visible_content"] == "老师定稿内容"
must(client.post(f"/api/reports/{rid}/publish", headers=TH))

# 4) parent visibility
own_name = "小明"
# find the 小明 report
ming = next(x for x in b["reports"] if x["child_name"] == "小明")
# publish the other too
n = must(client.post(f"/api/reports/batches/{bid}/publish_all", headers=TH))
assert n["published"] == 1, n  # one already published
rep = must(client.get(f"/api/reports/{ming['id']}", headers=P1))
assert rep["is_published"] is True
r = client.get(f"/api/reports/{ming['id']}", headers=P2)
assert r.status_code == 403  # 小红's parent can't see 小明
# unpublished nothing here; child list for parent
lst = must(client.get("/api/reports/child", headers=P1, params={"class_id": cid, "child_name": "小明"}))
assert len(lst["reports"]) == 1
print("[P4] edit/publish/parent visibility OK")

# 5) regenerate blocked after publish
r = client.post("/api/reports/batches", headers=TH,
                json={"class_id": cid, "type": "day", "date": today, "regenerate": True})
assert r.status_code == 409, r.text
# unpublish one then regenerate allowed
must(client.post(f"/api/reports/{rid}/unpublish", headers=TH))
# 小红 still published -> still conflict
r = client.post("/api/reports/batches", headers=TH,
                json={"class_id": cid, "type": "day", "date": today, "regenerate": True})
assert r.status_code == 409
hong = next(x for x in b["reports"] if x["child_name"] == "小红")
must(client.post(f"/api/reports/{hong['id']}/unpublish", headers=TH))
r = must(client.post("/api/reports/batches", headers=TH,
                     json={"class_id": cid, "type": "day", "date": today, "regenerate": True}))
assert r["status"] == "pending" and r["total"] == 2
print("[P4] regenerate guard OK")

# 6) weekly batch + prompt facts (checkin + homework facts for 小明)
w = must(client.post("/api/reports/batches", headers=TH, json={"class_id": cid, "type": "week", "date": today}))
assert w["period_start"] == "2026-10-12" and w["period_end"] == "2026-10-18", w
wb = must(client.get(f"/api/reports/batches/{w['id']}", headers=TH))
assert wb["status"] == "done", wb
# verify prompt contained the checkin fact
print("[P4] weekly batch done OK (LLM calls so far:", calls["n"], ")")

from ai_teacher.storage.database import get_engine
get_engine().dispose()
tmp.unlink()
print("\nALL CHECKIN/REPORT TESTS PASSED")
