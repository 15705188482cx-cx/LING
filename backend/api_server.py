# -*- coding: utf-8 -*-
"""FastAPI 入口：刘嘉玲 web 后端。

端口 8765，CORS 全开（阶段1 web 端 file:// 可访问）。
启动时实例化 LingBackend（加载 FAISS + DB + LLM 客户端）。

启动：
  python api_server.py
前提：tts_server.py 已起（:8880），或通过 LIUJIALING_URL 指定外部 TTS 服务。
"""
import base64
import asyncio
import io
import logging
import queue
import wave

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from sse_starlette import EventSourceResponse

from pathlib import Path

import config
from core import LingBackend
from stickers import pick_sticker
from errors import ChatError, RequestTrace, new_request_id, INVALID_INPUT
import idempotency
import user_profile as profile_store
import moments
import moments_worker
import rate_limit

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="刘嘉玲 Ling Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 统一 422 校验失败格式 → {ok:false, error:{code:INVALID_INPUT, ...}}
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    # 取第一条错误信息
    errs = exc.errors()
    msg = errs[0].get("msg", "输入校验失败") if errs else "输入校验失败"
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "request_id": new_request_id(),
            "error": {
                "code": INVALID_INPUT,
                "message": msg,
                "retryable": False,
            },
        },
    )

# 启动时加载（FAISS + DB + LLM），可能耗时几秒
# ASR 不在这里加载（避免与 ws_server 重复加载占内存）；/asr 代理转发到 ws_server :8766
backend = LingBackend()

# 表情包静态文件服务：前端通过 /stickers/撒娇/撒娇.png 访问
STICKERS_DIR = str(Path(__file__).resolve().parent / "stickers")
app.mount("/stickers", StaticFiles(directory=STICKERS_DIR), name="stickers")

# 朋友圈定时发圈线程（daemon，随进程退出；start 幂等，重复 import 不会起多个）
moments_worker.start(backend)


class ChatRequest(BaseModel):
    text: str
    client_message_id: str = ""  # 前端生成，用于幂等去重（V0.1 接收，V0.2 实现真正的幂等）

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text 不能为空")
        if len(v) > 2000:
            raise ValueError("text 超过 2000 字上限")
        return v


class ChatImageRequest(BaseModel):
    text: str = ""
    image: str  # base64 编码，不含 data: 前缀


class AsrRequest(BaseModel):
    audio: str  # base64 编码的 WAV，不含 data: 前缀
    sample_rate: int = 16000


def _chat_error_response(e: Exception, request_id: str) -> JSONResponse:
    """把异常转成统一错误响应。ChatError 用其 code，其他兜底 INTERNAL_ERROR。"""
    if isinstance(e, ChatError):
        return JSONResponse(
            status_code=e.status_code,
            content={
                "ok": False,
                "request_id": request_id,
                "error": e.to_dict(),
            },
        )
    logger.exception(f"[{request_id}] 未预期异常")
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "request_id": request_id,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "内部错误，请重试",
                "retryable": True,
            },
        },
    )


@app.post("/chat")
def chat(req: ChatRequest):
    """文字 → {ok, request_id, reply, emotion} 或 {ok:false, error}。

    client_message_id 命中幂等缓存时直接返回首次结果，不重调 LLM、不重复写历史。
    """
    request_id = new_request_id()
    # 幂等命中：重试/网络重发同一 client_message_id → 返回缓存，不重复处理
    cached = idempotency.get(req.client_message_id)
    if cached:
        logger.info(f"[{request_id}] 幂等命中 client_message_id={req.client_message_id}")
        return {
            "ok": True,
            "request_id": request_id,
            "reply": cached["reply"],
            "emotion": cached["emotion"],
            "idempotent": True,
        }

    trace = RequestTrace(request_id)
    try:
        with trace.stage("chat"):
            reply, emotion = backend.chat(req.text, trace=trace)
        # 成功后缓存结果，供后续重试/重发去重
        idempotency.put(req.client_message_id, reply, emotion)
        trace.log_summary("/chat 完成")
        return {
            "ok": True,
            "request_id": request_id,
            "reply": reply,
            "emotion": emotion,
        }
    except ChatError as e:
        trace.log_summary(f"/chat 失败({e.code})")
        return _chat_error_response(e, request_id)
    except Exception as e:
        trace.log_summary("/chat 未预期失败")
        return _chat_error_response(e, request_id)


@app.post("/chat/stream")
async def chat_stream_route(req: ChatRequest, request: Request):
    """流式文字聊天：SSE 推逐句文字 + emotion。

    复用 core.chat_stream()（同步生成器，yield (sentence, emotion)），用
    run_in_executor + queue 桥接到 async（同 ws_server.py:466-481 模式）。

    SSE 事件流：
      event: emotion  data: 日常     ← 初始情绪（首句前）
      event: chunk     data: 在呢，   ← 逐句文字（前端累加渲染 + 触发 TTS）
      event: chunk     data: 怎么了
      event: emotion   data: 撒娇     ← 最终情绪（全文入库后补正）
      event: done      data: {}       ← 流结束
      event: error     data: <msg>    ← 出错（前端置 failed）

    客户端断连（AbortController.abort）时 request.is_disconnected() 为真，
    生成器线程仍会跑完（同步 OpenAI stream 无法真停，已知短板），但不再推事件。
    """
    request_id = new_request_id()
    logger.info(f"[{request_id}] /chat/stream 开始 text={req.text!r}")

    async def event_gen():
        q: queue.Queue = queue.Queue()
        loop = asyncio.get_event_loop()

        def run_stream():
            """线程池里跑同步 chat_stream，把 yield 项塞进 queue。"""
            try:
                for sentence, emotion in backend.chat_stream(req.text):
                    q.put((sentence, emotion))
            except Exception as e:
                q.put(("__error__", str(e)))
                logger.error(f"[{request_id}] /chat/stream 生成失败: {e}", exc_info=True)
            q.put(("__done__", None))

        loop.run_in_executor(None, run_stream)

        full_reply = []
        final_emotion = "日常"
        try:
            while True:
                # 客户端断连则停止推事件（打断的核心）
                if await request.is_disconnected():
                    logger.info(f"[{request_id}] /chat/stream 客户端断连，停止推送")
                    break
                item = await loop.run_in_executor(None, q.get)
                sentence, emotion = item
                if sentence == "__done__":
                    yield {"event": "done", "data": "{}"}
                    break
                if sentence == "__error__":
                    yield {"event": "error", "data": emotion}
                    break
                # chat_stream yield 协议：
                #   ("", "日常")    初始 emotion
                #   ("句子", None)  逐句文本
                #   (None, "撒娇")  最终 emotion
                if emotion is not None and not sentence:
                    final_emotion = emotion
                    yield {"event": "emotion", "data": emotion}
                elif sentence:
                    full_reply.append(sentence)
                    yield {"event": "chunk", "data": sentence}
                elif emotion is not None:
                    final_emotion = emotion
                    yield {"event": "emotion", "data": emotion}
        finally:
            # 流结束后缓存完整结果，供后续非流式重试去重
            reply_text = "".join(full_reply)
            if reply_text:
                idempotency.put(req.client_message_id, reply_text, final_emotion)
            logger.info(f"[{request_id}] /chat/stream 结束 reply={reply_text!r} emotion={final_emotion}")

    return EventSourceResponse(event_gen())


@app.post("/chat/image")
def chat_with_image(req: ChatImageRequest):
    """带图的对话 → {reply, emotion, sticker}。

    image 为 base64 编码（不含 data: 前缀）。后端先用 VLM 把图片转成文字描述，
    再拼进 user message 走主对话流程。reply 末尾按 emotion 有概率附表情包。
    """
    request_id = new_request_id()
    try:
        reply, emotion = backend.chat_with_image(req.text, req.image)
        # 按情绪选表情包（无表情包时返回空字符串，前端不显示）
        sticker = pick_sticker(emotion)
        return {"reply": reply, "emotion": emotion, "sticker": sticker}
    except ChatError as e:
        return _chat_error_response(e, request_id)
    except Exception as e:
        logger.exception(f"[{request_id}] /chat/image 失败")
        return _chat_error_response(e, request_id)


@app.post("/video/frame")
def video_frame(req: ChatImageRequest):
    """视频通话时的对话：摄像头帧 + 文字 → {reply, emotion}。

    和 /chat/image 的区别：视频帧作为"她看到你"的背景上下文注入，
    VLM 描述画面里你在做什么/什么表情，让她自然地"看到"你后回复。
    前端应控制调用频率（每 5-10 秒一帧，或说话时采一帧），避免 VLM 过载。
    """
    request_id = new_request_id()
    try:
        reply, emotion = backend.chat_with_vision(req.text or "", req.image)
        return {"reply": reply, "emotion": emotion}
    except ChatError as e:
        return _chat_error_response(e, request_id)
    except Exception as e:
        logger.exception(f"[{request_id}] /video/frame 失败")
        return _chat_error_response(e, request_id)


@app.get("/tts")
def tts(text: str = Query(..., description="要合成语音的文本")):
    """文字 → wav 字节流。代理 mini_tts_server :8880。"""
    try:
        wav = backend.tts(text)
        return Response(
            content=wav,
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=tts.wav"},
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.exception("/tts 失败")
        return JSONResponse(
            status_code=502,
            content={"error": f"tts upstream failed: {e}"},
        )


@app.get("/health")
def health():
    """健康检查 + 资源就绪状态。

    status 三档：
    - ok        进程活 + 关键依赖（DB）可用
    - degraded  进程活但部分依赖降级（如 FAISS 没启用，记忆检索走兜底）
    - unavailable 不应出现（出现说明进程起不来，根本到不了这里）
    """
    memory_ok = backend.memory.enabled
    return {
        "status": "ok" if memory_ok else "degraded",
        "memory": memory_ok,
        "db": True,
        "user_id": backend.user_id,
    }


@app.get("/history")
def history(limit: int = Query(config.MAX_HISTORY, ge=1, le=200)):
    """最近 limit 条对话（正序）。"""
    return backend.history(limit=limit)


@app.post("/asr")
async def asr_transcribe(req: AsrRequest):
    """语音转文字（按住说话）：代理转发到 ws_server :8766 /asr。

    ASR 模型只在 ws_server 加载一次（省内存），api_server 代理转发。
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:{config.WS_PORT}/asr",
                json={"audio": req.audio, "sample_rate": req.sample_rate},
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        return JSONResponse(status_code=e.response.status_code, content=e.response.json())
    except Exception as e:
        logger.exception("/asr 代理失败")
        return JSONResponse(status_code=502, content={"error": f"asr upstream failed: {e}"})


@app.post("/reset")
def reset():
    """清空对话历史。"""
    backend.reset()
    return {"ok": True}


class ProfileRequest(BaseModel):
    name: str | None = None
    signature: str | None = None
    avatar: str | None = None  # base64 data URL；空串=清除自定义头像


@app.get("/profile")
def get_profile():
    """读取个人资料（名字/签名/头像）。avatar 为空时前端用默认头像。"""
    return profile_store.get_profile()


@app.put("/profile")
def update_profile(req: ProfileRequest):
    """更新个人资料，只改传入的非 None 字段。"""
    profile_store.set_profile(req.name, req.signature, req.avatar)
    return {"ok": True, "profile": profile_store.get_profile()}


# ---------- 朋友圈 Moments（V0.2）----------
# 契约见 BACKEND_INTEGRATION_V0.2.md §3.1。前端走 mock 兜底，这些接口到位即切换真数据。


class MomentCreateRequest(BaseModel):
    content: str
    images: list[str] = []

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content 不能为空")
        if len(v) > 2000:
            raise ValueError("content 超过 2000 字上限")
        return v

    @field_validator("images")
    @classmethod
    def images_max_nine(cls, v: list[str]) -> list[str]:
        if len(v) > 9:
            raise ValueError("images 最多 9 张")
        return v


class MomentLikeRequest(BaseModel):
    name: str = "我"


class MomentCommentRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text 不能为空")
        if len(v) > 500:
            raise ValueError("text 超过 500 字上限")
        return v


class MomentsConfigRequest(BaseModel):
    post_interval_sec: int


@app.get("/moments")
def list_moments(limit: int = Query(20, ge=1, le=100), before: float | None = Query(None)):
    """拉朋友圈列表（ts 降序，分页）。返回 {items, has_more}（裸数据，无 ok）。"""
    items, has_more = moments.list_moments(limit=limit, before=before)
    return {"items": items, "has_more": has_more}


@app.post("/moments")
def create_moment(req: MomentCreateRequest):
    """我发朋友圈。返回 {ok, id}。60s 内最多 5 条防误点狂发。"""
    if not rate_limit.check_post():
        return _chat_error_response(
            ChatError("UPSTREAM_RATE_LIMITED", "发太快啦，等一会儿再发", 429),
            new_request_id(),
        )
    mid = moments.add_moment("我", req.content, req.images)
    return {"ok": True, "id": mid}


@app.post("/moments/{moment_id}/like")
def toggle_like(moment_id: str, req: MomentLikeRequest):
    """点赞/取消点赞（幂等切换）。返回 {ok, liked, count}。"""
    liked, count = moments.toggle_like(moment_id, req.name)
    return {"ok": True, "liked": liked, "count": count}


@app.post("/moments/{moment_id}/comments")
def add_comment(moment_id: str, req: MomentCommentRequest):
    """我评论 → 触发 LLM 生成她的回复。返回 {ok, comment_id, reply, reply_emotion}。

    LLM 失败时仍存评论，用贴合语境的兜底回复保证 reply 非空（契约要求必填）。
    """
    import random
    request_id = new_request_id()
    if not rate_limit.check_comment():
        return _chat_error_response(
            ChatError("UPSTREAM_RATE_LIMITED", "评论太快啦，等一会儿再发", 429),
            request_id,
        )
    content = moments.get_moment_content(moment_id)
    if content is None:
        return _chat_error_response(
            ChatError(INVALID_INPUT, "朋友圈不存在", 404), request_id
        )
    try:
        reply, emotion = backend.reply_to_comment(content, req.text)
    except Exception:
        logger.exception(f"[{request_id}] 评论 LLM 回复失败，用兜底回复")
        # 按评论语气选兜底，比固定"嗯嗯"自然
        emotion = backend._guess_emotion(req.text, "")
        fallbacks = {
            "调情": ["嘿嘿", "讨厌啦", "你也是"],
            "撒娇": ["哼", "人家知道啦", "好吧好吧"],
            "焦急": ["嗯嗯看到了", "急什么嘛", "在呢在呢"],
            "冷淡": ["嗯", "哦", "知道了"],
            "日常": ["嘿嘿", "说得对", "嗯嗯"],
        }
        reply = random.choice(fallbacks.get(emotion, ["嗯嗯"]))
    cid = moments.add_comment(
        moment_id, "我", req.text, reply=reply, reply_emotion=emotion
    )
    return {"ok": True, "comment_id": cid, "reply": reply, "reply_emotion": emotion}


@app.get("/moments/new_count")
def moments_new_count(since: float = Query(..., description="unix 秒，统计 ts>since 的新动态数")):
    """红点未读数（只数 author=刘嘉玲 的新动态）。返回 {count}（裸数据，无 ok）。"""
    return {"count": moments.count_new_since(since)}


@app.get("/moments/config")
def moments_get_config():
    """读取发圈频率配置。返回 {post_interval_sec}（裸数据，无 ok）。"""
    return moments.get_config()


@app.post("/moments/config")
def moments_set_config(req: MomentsConfigRequest):
    """调整发圈频率。返回 {ok}。下个发圈周期自动生效。"""
    moments.set_post_interval(req.post_interval_sec)
    return {"ok": True}


if __name__ == "__main__":
    logger.info(
        f"Ling backend 启动 :{config.PORT} "
        f"(model={config.LLM_MODEL}, tts={config.LIUJIALING_URL})"
    )
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
