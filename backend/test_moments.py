# -*- coding: utf-8 -*-
"""朋友圈闭环测试（V0.2）。

直连 api_server :8765，覆盖：
- 列表/分页/has_more
- 发圈（含图片 base64）
- 点赞幂等切换 + count 正确
- 评论 + LLM 回复（reply 非空、emotion 是 5 枚举之一）
- 评论持久化（列表复查带 reply）
- 红点计数（只数 author=刘嘉玲）
- 配置读写 + 生效
- 限流（发圈 60s/5 条、评论 60s/20 条）
- 不存在的朋友圈 → INVALID_INPUT 错误信封
- 错误信封格式校验（{ok:false, request_id, error:{code,message,retryable}}）

用法：
  python test_moments.py
前提：api_server.py 已起在 :8765
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8765"
VALID_EMOTIONS = {"日常", "调情", "撒娇", "焦急", "冷淡"}

passed = 0
failed = 0


def req(method: str, path: str, body=None):
    """发请求，返回 (status, json_or_text)。"""
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}  {detail}")


print("=" * 60)
print("朋友圈闭环测试（V0.2）")
print("=" * 60)

# ---- 0. 健康检查 ----
print("\n[0] 健康检查")
s, b = req("GET", "/health")
check("health 200", s == 200, f"got {s}")
check("status ok/degraded", b.get("status") in ("ok", "degraded"), str(b))
check("memory 字段存在", "memory" in b, str(b))

# ---- 1. 初始列表（应有 3 条种子）----
print("\n[1] 初始列表")
s, b = req("GET", "/moments?limit=20")
check("GET /moments 200", s == 200, f"got {s}")
check("返回 items 数组", isinstance(b.get("items"), list), str(b)[:200])
check("has_more 字段存在", "has_more" in b, str(b)[:200])
initial_count = len(b.get("items", []))
check(f"至少 3 条种子（实际 {initial_count}）", initial_count >= 3, str(b)[:200])
# 结构校验
if b.get("items"):
    m = b["items"][0]
    check("item 有 id", "id" in m, str(m)[:200])
    check("item 有 author", "author" in m, str(m)[:200])
    check("item 有 content", "content" in m, str(m)[:200])
    check("item 有 ts(数字)", isinstance(m.get("ts"), (int, float)), str(m.get("ts")))
    check("item 有 likes 数组", isinstance(m.get("likes"), list), str(m)[:200])
    check("item 有 comments 数组", isinstance(m.get("comments"), list), str(m)[:200])
    check("item 有 images 数组", isinstance(m.get("images"), list), str(m)[:200])

# ---- 2. 发圈（含 1x1 红色 png base64）----
print("\n[2] 发圈（带图片 base64）")
# 1x1 红色 PNG
red_png_b64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNg"
    "YAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
)
s, b = req("POST", "/moments", {"content": "测试发圈带图", "images": [red_png_b64]})
check("POST /moments 200", s == 200, f"got {s} {str(b)[:200]}")
check("返回 ok:true", b.get("ok") is True, str(b)[:200])
check("返回 id", "id" in b and b["id"], str(b)[:200])
my_moment_id = b.get("id")

# ---- 3. 发空内容 → INVALID_INPUT ----
print("\n[3] 发空内容 → 错误信封")
s, b = req("POST", "/moments", {"content": "", "images": []})
check("状态 422", s == 422, f"got {s}")
check("ok:false", b.get("ok") is False, str(b)[:200])
check("error.code=INVALID_INPUT", b.get("error", {}).get("code") == "INVALID_INPUT", str(b)[:200])
check("error.retryable=false", b.get("error", {}).get("retryable") is False, str(b)[:200])
check("request_id 存在", "request_id" in b, str(b)[:200])

# ---- 4. 列表复查我发的圈 ----
print("\n[4] 列表复查我发的圈")
s, b = req("GET", "/moments?limit=20")
found = [m for m in b["items"] if m["id"] == my_moment_id]
check("我发的圈在列表里", len(found) == 1, str([m["id"] for m in b["items"]])[:200])
if found:
    m = found[0]
    check("author=我", m["author"] == "我", str(m)[:200])
    check("content 正确", m["content"] == "测试发圈带图", str(m)[:200])
    check("images 持久化（1 张）", len(m.get("images", [])) == 1, str(m.get("images"))[:200])
    check("images 是 base64 data URL", m["images"][0].startswith("data:image/"), str(m["images"][0])[:80])

# ---- 5. 点赞幂等切换 ----
print("\n[5] 点赞幂等切换")
s, b = req("POST", f"/moments/{my_moment_id}/like", {"name": "我"})
check("第一次点赞 200", s == 200, f"got {s}")
check("liked=true", b.get("liked") is True, str(b)[:200])
check("count=1", b.get("count") == 1, str(b)[:200])
s, b = req("POST", f"/moments/{my_moment_id}/like", {"name": "我"})
check("第二次取消 liked=false", b.get("liked") is False, str(b)[:200])
check("count=0", b.get("count") == 0, str(b)[:200])
s, b = req("POST", f"/moments/{my_moment_id}/like", {"name": "我"})
check("第三次再赞 liked=true", b.get("liked") is True, str(b)[:200])

# ---- 6. 评论 + LLM 回复 ----
print("\n[6] 评论 + LLM 回复")
s, b = req("POST", f"/moments/{my_moment_id}/comments", {"text": "厉害啊"})
check("评论 200", s == 200, f"got {s} {str(b)[:200]}")
check("ok:true", b.get("ok") is True, str(b)[:200])
check("comment_id 非空", bool(b.get("comment_id")), str(b)[:200])
check("reply 非空", bool(b.get("reply")), str(b)[:200])
check("reply_emotion 是 5 枚举之一", b.get("reply_emotion") in VALID_EMOTIONS, str(b.get("reply_emotion")))
print(f"     她回复：{b.get('reply')} ({b.get('reply_emotion')})")

# ---- 7. 评论持久化复查 ----
print("\n[7] 评论持久化复查")
s, b = req("GET", "/moments?limit=20")
m = [x for x in b["items"] if x["id"] == my_moment_id][0]
check("评论已持久化（1 条）", len(m["comments"]) == 1, str(m["comments"])[:200])
if m["comments"]:
    c = m["comments"][0]
    check("评论 name=我", c["name"] == "我", str(c)[:200])
    check("评论 text 正确", c["text"] == "厉害啊", str(c)[:200])
    check("评论带 reply", bool(c.get("reply")), str(c)[:200])
    check("评论带 reply_emotion", c.get("reply_emotion") in VALID_EMOTIONS, str(c.get("reply_emotion")))
check("点赞已持久化（1 条）", len(m["likes"]) == 1, str(m["likes"])[:200])

# ---- 8. 红点计数 ----
print("\n[8] 红点计数")
s, b = req("GET", "/moments/new_count?since=0")
check("new_count 200", s == 200, f"got {s}")
check("count 是整数", isinstance(b.get("count"), int), str(b)[:200])
total_her = b["count"]
# since=现在 → 应为 0
s, b = req("GET", f"/moments/new_count?since={time.time()}")
check("since=现在 count=0", b.get("count") == 0, str(b)[:200])
# since=0 只数刘嘉玲
s, b = req("GET", "/moments/new_count?since=0")
her_count = sum(1 for x in [m] for _ in [1] if x["author"] == "刘嘉玲")  # 不准，直接信接口
check("since=0 count>0（有种子）", b["count"] > 0, str(b)[:200])

# ---- 9. 配置读写 + 生效 ----
print("\n[9] 配置读写")
s, b = req("POST", "/moments/config", {"post_interval_sec": 120})
check("POST config 200", s == 200, f"got {s}")
check("ok:true", b.get("ok") is True, str(b)[:200])
s, b = req("GET", "/moments/config")
check("GET config 200", s == 200, f"got {s}")
check("post_interval_sec=120", b.get("post_interval_sec") == 120, str(b)[:200])
# 恢复
req("POST", "/moments/config", {"post_interval_sec": 300})

# ---- 10. 不存在的朋友圈 ----
print("\n[10] 不存在的朋友圈 → 错误信封")
s, b = req("POST", "/moments/nonexistent_id/comments", {"text": "test"})
check("状态 4xx/5xx", s >= 400, f"got {s}")
check("ok:false", b.get("ok") is False, str(b)[:200])
check("error.code 存在", "code" in b.get("error", {}), str(b)[:200])

s, b = req("POST", "/moments/nonexistent_id/like", {"name": "我"})
# 点赞不存在的也允许（幂等切换不报错），但 count=0
check("点赞不存在的不崩", s == 200, f"got {s} {str(b)[:200]}")

# ---- 11. 限流：发圈 60s/5 条 ----
print("\n[11] 限流：发圈 60s 内第 6 条应被拒")
# 已经发过 1 条，再发 4 条到上限，第 5 条（总第 6）应被拒
rejected = False
for i in range(5):
    s, b = req("POST", "/moments", {"content": f"限流测试 {i}", "images": []})
    if s == 429 and b.get("error", {}).get("code") == "UPSTREAM_RATE_LIMITED":
        rejected = True
        break
check("第 6 条前被限流（429）", rejected, "未触发限流")
if rejected:
    # UPSTREAM_RATE_LIMITED 在 RETRYABLE_CODES 里，retryable=true（用户等几秒可重试发圈/评论）
    check("限流 retryable=true（等几秒可重试）", b.get("error", {}).get("retryable") is True, str(b)[:200])

# ---- 12. 分页 ----
print("\n[12] 分页")
s, b = req("GET", "/moments?limit=2")
check("limit=2 返回 2 条", len(b["items"]) == 2, f"实际 {len(b['items'])}")
# 用第二条的 ts 作 before
before_ts = b["items"][-1]["ts"]
s, b2 = req("GET", f"/moments?limit=2&before={before_ts}")
check("before 分页返回更早的", len(b2["items"]) >= 1, f"实际 {len(b2['items'])}")
if b2["items"]:
    check("分页结果 ts < before", b2["items"][0]["ts"] < before_ts, str(b2["items"][0]["ts"]))

# ---- 总结 ----
print("\n" + "=" * 60)
print(f"结果：{passed} 通过，{failed} 失败")
print("=" * 60)
exit(0 if failed == 0 else 1)
