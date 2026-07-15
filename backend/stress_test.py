# -*- coding: utf-8 -*-
"""压测脚本：连续发 20 条短消息，输出成功率、P50/P95/P99 耗时与失败分类。

不调 /reset，不污染正式用户历史（消息会进 DB 但不影响功能）。
用法：python stress_test.py [条数，默认20]
"""
import sys
import time
import statistics
import requests

API = "http://127.0.0.1:8765"

# 20 条不同的短消息，模拟真实对话
MESSAGES = [
    "在吗", "干嘛呢", "吃了吗", "想你了", "今天怎么样",
    "下班了吗", "好累啊", "抱抱", "你好烦", "哈哈",
    "睡了吗", "晚安", "早安", "我回来了", "出去玩了",
    "下雨了", "好热", "无聊", "陪我聊天", "爱你哦",
]


def run(n: int):
    print(f"压测开始：连续发 {n} 条消息\n")
    results = []  # [(ok, ms, error_code)]
    for i in range(n):
        msg = MESSAGES[i % len(MESSAGES)]
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{API}/chat",
                json={"text": msg, "client_message_id": f"stress_{i}_{int(t0*1000)}"},
                timeout=60,
            )
            ms = (time.monotonic() - t0) * 1000
            body = r.json()
            if r.status_code == 200 and body.get("ok"):
                reply = body.get("reply", "")[:20]
                results.append((True, ms, None))
                print(f"  [{i+1:2d}/{n}] ✅ {ms:5.0f}ms  {msg} → {reply}")
            else:
                code = body.get("error", {}).get("code", "UNKNOWN") if isinstance(body, dict) else "UNKNOWN"
                results.append((False, ms, code))
                print(f"  [{i+1:2d}/{n}] ❌ {ms:5.0f}ms  {msg} → {code}")
        except requests.exceptions.Timeout:
            ms = (time.monotonic() - t0) * 1000
            results.append((False, ms, "TIMEOUT"))
            print(f"  [{i+1:2d}/{n}] ❌ {ms:5.0f}ms  {msg} → TIMEOUT")
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            results.append((False, ms, type(e).__name__))
            print(f"  [{i+1:2d}/{n}] ❌ {ms:5.0f}ms  {msg} → {type(e).__name__}: {e}")

    # 汇总
    print("\n" + "=" * 50)
    print("  压测汇总")
    print("=" * 50)
    ok_count = sum(1 for ok, _, _ in results if ok)
    fail_count = n - ok_count
    latencies = [ms for ok, ms, _ in results if ok]
    print(f"  总数: {n}")
    print(f"  成功: {ok_count} ({ok_count/n*100:.0f}%)")
    print(f"  失败: {fail_count} ({fail_count/n*100:.0f}%)")

    if latencies:
        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[-1]
        p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[-1]
        print(f"  耗时 P50: {p50:.0f}ms")
        print(f"  耗时 P95: {p95:.0f}ms")
        print(f"  耗时 P99: {p99:.0f}ms")
        print(f"  耗时均值: {statistics.mean(latencies):.0f}ms")

    if fail_count:
        print(f"\n  失败分类:")
        from collections import Counter
        codes = Counter(code for _, _, code in results if code)
        for code, cnt in codes.most_common():
            print(f"    {code}: {cnt}")

    print()
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sys.exit(run(n))
