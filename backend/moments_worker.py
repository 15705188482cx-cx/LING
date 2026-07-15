# -*- coding: utf-8 -*-
"""朋友圈定时发圈后台线程。

按 moments_config.post_interval_sec 间隔，从模板库选一条（或 LLM 生成）以「刘嘉玲」
身份发圈。每周期重读配置——配置变更后下个周期自动生效，无需重启。

daemon 线程，随进程退出。LLM 失败不影响线程存活（跳过本轮，等下个周期再试）。
"""
import logging
import threading

import moments

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def start(backend) -> None:
    """启动定时发圈线程（幂等：重复调用不会起多个）。backend 为 LingBackend 实例。"""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_loop, args=(backend,), name="moments-worker", daemon=True
    )
    _thread.start()
    logger.info("朋友圈定时发圈线程已启动")


def stop() -> None:
    """停止线程（测试用，正常退出靠 daemon）。"""
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)


def _loop(backend) -> None:
    """主循环：读间隔 → 等待 → 发圈 → 重复。"""
    while not _stop.is_set():
        try:
            interval = moments.get_config()["post_interval_sec"]
        except Exception:
            interval = 300
        # wait 返回 True 表示被 stop() 唤醒 → 退出
        if _stop.wait(interval):
            break
        try:
            _post_one(backend)
        except Exception:
            logger.exception("定时发圈失败，跳过本轮")


def _post_one(backend) -> None:
    """发一条朋友圈：模板优先（用完自动重置循环复用），LLM 偶尔生成避免重复感。

    模板库用完时重置 used=0 让模板循环复用（15 条够用），而不是每次都调 LLM
    （高频发圈档一天上千次调用，成本和稳定性都不划算）。仅在模板全部用过的
    那一轮用 LLM 生成一条新鲜内容，然后重置模板继续循环。
    """
    tpl = moments.pick_template()
    if tpl:
        content, images = tpl
        logger.info("定时发圈（模板）")
    else:
        # 模板全用过：LLM 生成一条新鲜的，然后重置模板库供下轮循环
        try:
            content = backend.generate_moment()
        except Exception:
            # LLM 也挂了：重置模板随便选一条，保证发圈不中断
            logger.exception("LLM 生成朋友圈失败，重置模板库兜底")
            moments.reset_templates()
            tpl = moments.pick_template()
            content = tpl[0] if tpl else "今天又是平淡的一天"
        images = []
        moments.reset_templates()
        logger.info("定时发圈（LLM 生成 + 模板库已重置）")
    moments.add_moment("刘嘉玲", content, images, source="来自朋友圈")
