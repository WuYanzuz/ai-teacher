"""E2E test for the backend API.

Assumes uvicorn is running on http://127.0.0.1:8000.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"


def main() -> int:
    print("=" * 60)
    print("  Backend E2E test")
    print("=" * 60)

    # 1. Teacher dev_login
    print("\n[1] Teacher dev_login")
    r = requests.post(f"{BASE}/api/auth/dev_login", json={
        "openid": "teacher_test_001", "name": "张老师", "role": "teacher",
    })
    r.raise_for_status()
    teacher = r.json()
    teacher_token = teacher["token"]
    print(f"   teacher: id={teacher['user']['id']}, name={teacher['user']['name']}")
    teacher_h = {"Authorization": f"Bearer {teacher_token}"}

    # 2. Create class
    print("\n[2] Teacher creates class")
    r = requests.post(f"{BASE}/api/classes", json={"name": "小一班"}, headers=teacher_h)
    r.raise_for_status()
    cls = r.json()
    class_id = cls["id"]
    code = cls["code"]
    print(f"   class id={class_id}, code={code}, role={cls['role']}")

    # 3. Parent dev_login
    print("\n[3] Parent dev_login")
    r = requests.post(f"{BASE}/api/auth/dev_login", json={
        "openid": "parent_test_001", "name": "小明妈", "role": "parent",
    })
    r.raise_for_status()
    parent = r.json()
    parent_token = parent["token"]
    parent_h = {"Authorization": f"Bearer {parent_token}"}
    print(f"   parent: id={parent['user']['id']}, name={parent['user']['name']}")

    # 4. Parent joins class
    print("\n[4] Parent joins class with code")
    r = requests.post(f"{BASE}/api/classes/join", json={
        "code": code, "child_name": "小明",
    }, headers=parent_h)
    r.raise_for_status()
    print(f"   joined: {r.json()}")

    # 5. Parent uploads homework (image)
    print("\n[5] Parent uploads homework image")
    img_path = Path("test/75c4e54ae69cde4aa40f57eef9f886f7.jpg")
    assert img_path.exists(), f"missing {img_path}"
    with img_path.open("rb") as f:
        r = requests.post(
            f"{BASE}/api/homework/upload",
            files={"file": (img_path.name, f, "image/jpeg")},
            data={"class_id": str(class_id), "child_name": "小明"},
            headers=parent_h,
        )
    r.raise_for_status()
    hw = r.json()
    hw_id = hw["id"]
    print(f"   uploaded: id={hw_id}, child={hw['child_name']}, type={hw['media_type']}")
    print(f"   media_url={hw['media_url']}")
    print(f"   initial feedback={hw.get('polished_feedback')!r}")

    # 6. Wait for background AI processing
    print("\n[6] Wait up to 30s for background AI processing ...")
    for i in range(30):
        time.sleep(1)
        r = requests.get(f"{BASE}/api/homework/{hw_id}", headers=teacher_h)
        r.raise_for_status()
        d = r.json()
        if d.get("polished_feedback") or d.get("raw_feedback"):
            print(f"   done after {i+1}s")
            break
    else:
        print("   TIMEOUT")
    print()
    print("=" * 60)
    print("  Result")
    print("=" * 60)
    print(f"  小朋友: {d['child_name']}")
    print(f"  类型:   {d['media_type']}")
    print(f"  ASR:    {d.get('transcript')}")
    print(f"  是作业: {d.get('is_homework')}")
    print(f"  点评:")
    print("  ---")
    for line in (d.get('polished_feedback') or '').split("\n"):
        print(f"  {line}")

    # 7. Teacher lists homework
    print("\n[7] Teacher lists all homework in class")
    r = requests.get(f"{BASE}/api/homework?class_id={class_id}", headers=teacher_h)
    r.raise_for_status()
    items = r.json()
    print(f"   total: {len(items)}")
    for it in items:
        print(f"   - id={it['id']} child={it['child_name']} type={it['media_type']} "
              f"is_homework={it['is_homework']} feedback={it.get('polished_feedback','')[:50]}...")

    # 8. Teacher acks
    print("\n[8] Teacher acks")
    r = requests.post(f"{BASE}/api/homework/{hw_id}/ack", headers=teacher_h)
    r.raise_for_status()
    print(f"   ack: {r.json().get('teacher_review')}")

    print("\n✅ E2E test passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.exceptions.RequestException as e:
        print(f"\n❌ HTTP error: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"   status: {e.response.status_code}", file=sys.stderr)
            print(f"   body: {e.response.text[:500]}", file=sys.stderr)
        sys.exit(1)
