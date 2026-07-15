# -*- coding: utf-8 -*-
"""独立 TTS 服务 - 刘嘉玲 GPT-SoVITS 音色。

ling 项目自用，逻辑照搬 mini_tts_server.py（含 torchaudio monkey-patch）。
需通过环境变量 GPT_SOVITS_DIR 指定 GPT-SoVITS 引擎目录（约 26GB，不入仓库）。
引擎来源：https://github.com/RVC-Boss/GPT-SoVITS

启动（必须用装了 torch/GPT-SoVITS 依赖的 venv，如 gsv-env）：
  python tts_server.py

接口：
  GET  /health            -> {"status":"ok","warmup_done":bool}
  POST /v1/audio/speech   body {"text":"..."} -> audio/wav
"""
import io
import os
import sys
import threading
import atexit

# ---------- 路径配置（通过环境变量配置，不再硬编码 Create-Ex） ----------

GPT_SOVITS_DIR = os.environ.get("GPT_SOVITS_DIR", "")
if GPT_SOVITS_DIR:
    os.chdir(GPT_SOVITS_DIR)
    sys.path.insert(0, GPT_SOVITS_DIR)
    sys.path.insert(0, os.path.join(GPT_SOVITS_DIR, "GPT_SoVITS"))
else:
    print("[TTS] 警告：未配置 GPT_SOVITS_DIR，TTS 服务无法启动", flush=True)

# CUDA DLL 路径（gsv-env 的 site-packages/nvidia/*/bin）
NVIDIA_DIR = os.path.join(
    os.path.dirname(sys.executable), "..", "Lib", "site-packages", "nvidia"
)
if os.path.isdir(NVIDIA_DIR):
    for sub in os.listdir(NVIDIA_DIR):
        bin_dir = os.path.join(NVIDIA_DIR, sub, "bin")
        if os.path.isdir(bin_dir):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]

# 模型权重（get_tts_wav 依赖这两个环境变量，相对 GPT_SOVITS_DIR 的路径）
# 权重文件需自行训练/下载后放入 GPT-SoVITS 的对应权重目录
os.environ.setdefault(
    "gpt_path",
    os.environ.get("TTS_GPT_PATH", "GPT_SoVITS/GPT_weights_v2Pro/liujialing-e6.ckpt"),
)
os.environ.setdefault(
    "sovits_path",
    os.environ.get(
        "TTS_SOVITS_PATH", "GPT_SoVITS/SoVITS_weights_v2Pro/liujialing_e12_s600.pth"
    ),
)

# 参考音频（本地副本，复用刘嘉玲音色）
from pathlib import Path as _Path  # noqa: E402

_REF_DEFAULT = str(_Path(__file__).resolve().parent / "assets" / "ref_liu.wav")
REF_AUDIO_PATH = os.environ.get("TTS_REF_AUDIO", _REF_DEFAULT)
REF_TEXT = "她可能是想陪她对象吧"

# 推理参数（与 baseline 同款，稍慢一点）
TTS_PARAMS = {
    "prompt_language": "中文",
    "text_language": "中文",
    "top_p": 1,
    "temperature": 1,
    "speed": 0.93,
    "pause_second": 0.4,
}


# ---------- torchaudio monkey-patch（绕开 torchaudio 依赖） ----------
import importlib.machinery
import importlib.util
import soundfile as sf
import numpy as np
import torch
import scipy.signal

_fake_spec = importlib.machinery.ModuleSpec("torchaudio", None)
_fake_ta = importlib.util.module_from_spec(_fake_spec)


def patched_load(path):
    """soundfile 替代 torchaudio.load: 返回 (tensor, sample_rate)"""
    audio, sr = sf.read(path)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
    else:
        audio = audio.T
    return torch.from_numpy(audio.astype(np.float32)), sr


class _ResampleTransform:
    """Fake torchaudio.transforms.Resample：用 scipy.signal.resample_poly 实现."""
    def __init__(self, orig_freq, new_freq, **kwargs):
        from math import gcd
        g = gcd(orig_freq, new_freq)
        self.up = new_freq // g
        self.down = orig_freq // g
        self.orig_freq = orig_freq
        self.new_freq = new_freq

    def to(self, device):
        self.device = device
        return self

    def __call__(self, waveform):
        if self.orig_freq == self.new_freq:
            return waveform
        arr = waveform.detach().cpu().numpy()
        resampled = scipy.signal.resample_poly(arr, self.up, self.down, axis=-1)
        out = torch.from_numpy(resampled).to(waveform.device).type(waveform.dtype)
        return out


class _TransformsMod:
    Resample = staticmethod(_ResampleTransform)


_fake_ta.load = patched_load
_fake_ta.transforms = _TransformsMod
sys.modules["torchaudio"] = _fake_ta

# jieba_fast 是 jieba 的 C 加速版，API 完全兼容。gsv-env 没装（需 C++ 编译），
# 这里用纯 jieba 顶替，避免改 GPT-SoVITS 源码。
import jieba  # noqa: E402
sys.modules["jieba_fast"] = jieba

from GPT_SoVITS.inference_webui import get_tts_wav  # noqa: E402


# ---------- 合成核心 ----------

def _synthesize(text: str) -> tuple[int, bytes]:
    """核心合成函数，返回 (sample_rate, wav_bytes)。"""
    if not text or not text.strip():
        raise ValueError("text is empty")

    synth = get_tts_wav(
        ref_wav_path=REF_AUDIO_PATH,
        prompt_text=REF_TEXT,
        text=text.strip(),
        **TTS_PARAMS,
    )
    last = None
    for item in synth:
        last = item

    if last is None:
        raise RuntimeError("get_tts_wav returned no results")

    sr, audio = last
    # 温和音量提升 1.2x，超 0.95 软削顶防失真
    audio = audio.astype(np.float32) * 1.2
    peak = float(np.max(np.abs(audio)))
    if peak > 0.95:
        audio = audio * (0.95 / peak)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="wav")
    return sr, buf.getvalue()


# ---------- warmup（后台加载模型） ----------

_warmup_done = threading.Event()


def _warmup():
    """启动时调一次空推，加载模型到 GPU。"""
    print("[tts_server] 加载 GPT-SoVITS 模型...", flush=True)
    synth = get_tts_wav(
        ref_wav_path=REF_AUDIO_PATH,
        prompt_text=REF_TEXT,
        text="启动",
        **TTS_PARAMS,
    )
    for _ in synth:
        pass
    print("[tts_server] 模型加载完成！", flush=True)


def _warmup_thread():
    try:
        _warmup()
    finally:
        _warmup_done.set()


threading.Thread(target=_warmup_thread, daemon=True).start()


# ---------- HTTP 接口 ----------

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response, JSONResponse  # noqa: E402

app = FastAPI(title="Ling TTS", docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {"status": "ok", "warmup_done": _warmup_done.is_set()}


@app.post("/v1/audio/speech")
async def synthesize(request: Request):
    """body: {"text": "..."} -> audio/wav"""
    try:
        body = await request.body()
        import json
        try:
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, dict):
                text = data.get("text") or data.get("input") or ""
            else:
                text = str(data)
        except Exception:
            text = body.decode("utf-8", errors="ignore").strip()

        text = text.replace("{prompt_text}", "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "empty text"})

        _warmup_done.wait(timeout=300)
        sr, wav_bytes = _synthesize(text)
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"X-Sample-Rate": str(sr),
                     "Content-Disposition": "inline; filename=tts.wav"},
        )
    except Exception as e:
        import traceback
        print(f"[tts_server] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    print("[tts_server] starting on :8880 ...", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8880, log_level="info")
