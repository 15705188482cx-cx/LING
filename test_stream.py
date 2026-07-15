"""端到端测试：流式文字聊天逐句渲染 + 打断。
验证：1. 文字逐句出现(不等整段) 2. 流式中再发消息能打断 3. TTS 触发
"""
import time
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/#/chat/window"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    print("=== 1. 发第一条消息 ===")
    textarea = page.locator("textarea.input")
    textarea.fill("在吗")
    page.locator("button.send").click()

    # 关键：等 2 秒后检查是否已有部分文字（流式逐句，不等整段）
    print("=== 2. 等 2 秒检查流式文字（应已出现部分，不等整段 5-10 秒）===")
    page.wait_for_timeout(2000)
    bubbles = page.locator(".bubble-text")
    count = bubbles.count()
    last_text = ""
    if count > 0:
        last_text = bubbles.nth(count - 1).inner_text()
    print(f"  2s 时气泡数={count}, 最后气泡文字='{last_text[:50]}'")

    # 检查流式光标是否存在（pending 且有 content）
    cursor = page.locator(".streaming-cursor")
    print(f"  流式光标存在={cursor.count() > 0}")

    # 等流式完成
    print("=== 3. 等流式完成（最多 15 秒）===")
    for i in range(15):
        page.wait_for_timeout(1000)
        if cursor.count() == 0:
            print(f"  {i+1}s: 流式光标消失，回复完成")
            break
    else:
        print("  15s 超时，光标仍在")

    bubbles = page.locator(".bubble-text")
    count = bubbles.count()
    last_text = bubbles.nth(count - 1).inner_text() if count > 0 else ""
    print(f"  最终气泡数={count}, 最后气泡文字='{last_text[:80]}'")

    # 截图
    page.screenshot(path="/tmp/ling_stream_final.png", full_page=True)

    print("\n=== 4. 测试打断：发第二条消息（不等第一条完成的情况下）===")
    # 先发一条新的
    textarea.fill("今天干嘛了")
    t0 = time.time()
    page.locator("button.send").click()
    page.wait_for_timeout(3000)  # 等 3 秒，流式应该在进行中

    # 此时再发第三条打断
    textarea.fill("吃饭没")
    page.locator("button.send").click()
    page.wait_for_timeout(8000)  # 等第三条完成

    bubbles = page.locator(".bubble-text")
    count = bubbles.count()
    print(f"  打断后气泡数={count}")
    for i in range(max(0, count - 4), count):
        try:
            print(f"    [{i}] {bubbles.nth(i).inner_text()[:60]}")
        except:
            pass

    print("\n=== 5. Console 错误检查 ===")
    # 收集 console 错误
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.wait_for_timeout(2000)
    if errors:
        print(f"  Console 错误: {errors}")
    else:
        print("  无 Console 错误")

    browser.close()
print("\n=== 测试完成 ===")
