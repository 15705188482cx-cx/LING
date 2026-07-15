# -*- coding: utf-8 -*-
"""向量记忆库：把录音转写的语义段存进 FAISS，对话时检索相关记忆。

架构：
  - 切块：以 emotion.json 的语义段为基点，每条 = 该段 + 前后各 2 段（同录音内）
  - Embedding：bge-small-zh-v1.5（本地，中文优化，512 维）
  - 向量库：FAISS IndexFlatIP（内积相似度，向量需 L2 归一化）
  - 存储：FAISS index 文件 + JSON 元数据文件配套

用法：
  store = MemoryStore(slug="lijialing")
  store.build_from_emotion_json(["H:/Sounds/录音文本/emotion.json"])
  results = store.search("你还记得潮汕那次吗", top_k=5)
"""
import os
import json
import shutil
from pathlib import Path
from typing import Optional

# ---- 模型缓存路径：默认 E 盘，可用 HF_HOME 环境变量覆盖 ----
# 首次运行会下载 bge-small-zh-v1.5 模型到此目录，需联网；已缓存后离线可用
os.environ.setdefault("HF_HOME", os.environ.get("HF_HOME", "E:/Hermes/hf_cache"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# 知识库根目录：指向 backend/assets/knowledge/{slug}
# memory_store.py 位于 backend/lib/，parent 即 backend/
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
# 上下文窗口：每条 chunk = 中心段 + 前后各 N 段
CONTEXT_WINDOW = 2


class MemoryStore:
    """向量记忆库：建库 / 入库 / 检索 / 持久化"""

    def __init__(self, slug: str = "lijialing",
                 base_dir: Optional[Path] = None,
                 model_name: str = EMBEDDING_MODEL):
        self.slug = slug
        if base_dir is None:
            base_dir = ASSETS_DIR / "knowledge" / slug
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.base_dir / "memory.faiss"
        self.meta_path = self.base_dir / "memory_meta.json"
        self.model_name = model_name

        self._model = None       # 延迟加载 embedding 模型
        self._index = None       # FAISS index
        self._metas: list[dict] = []  # 元数据（和 index 一一对应）

    # ============================================================
    # Embedding 模型（延迟加载）
    # ============================================================
    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"加载 embedding 模型: {self.model_name}", flush=True)
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=os.environ.get("HF_HOME", None),
            )
            print("  ✅ 模型加载完成", flush=True)
        return self._model

    # ============================================================
    # 切块：语义段 + 上下文
    # ============================================================
    def _make_chunks(self, segments: list[dict]) -> list[dict]:
        """把 emotion.json 的语义段切成带上下文的 chunk。

        每个 chunk = segments[center-N : center+N+1] 的文本拼接，
        保留中心段的元数据（时间、说话人、情绪）。
        """
        chunks = []
        n = len(segments)
        for i, seg in enumerate(segments):
            lo = max(0, i - CONTEXT_WINDOW)
            hi = min(n, i + CONTEXT_WINDOW + 1)
            window = segments[lo:hi]
            # 拼接文本，用说话人标签标注
            parts = []
            for w in window:
                tag = f"[{w['speaker']}]" if "speaker" in w else ""
                parts.append(f"{tag} {w['text']}".strip())
            chunk_text = " ".join(parts)

            chunks.append({
                "text": chunk_text,
                "center_text": seg["text"],
                "rec": seg.get("rec", 0),
                "file": seg.get("file", ""),
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "speaker": seg.get("speaker", ""),
                "emotion": seg.get("emotion", ""),
            })
        return chunks

    # ============================================================
    # 建库 / 入库
    # ============================================================
    def build_from_emotion_json(self, json_paths: list[str],
                                append: bool = False) -> int:
        """从 emotion.json 文件批量建库。

        Args:
            json_paths: emotion.json 文件路径列表
            append: True=追加到现有库；False=重建

        Returns:
            入库的 chunk 总数
        """
        import numpy as np
        import faiss

        # 收集所有语义段
        all_segments = []
        for jp in json_paths:
            with open(jp, "r", encoding="utf-8") as f:
                segs = json.load(f)
            print(f"  读取 {Path(jp).name}: {len(segs)} 段", flush=True)
            all_segments.extend(segs)

        if not all_segments:
            print("⚠️ 没有语义段可入库", flush=True)
            return 0

        # 切块
        chunks = self._make_chunks(all_segments)
        print(f"  切块完成: {len(chunks)} 个 chunk（上下文窗口={CONTEXT_WINDOW}）",
              flush=True)

        # 如果追加，先加载已有的
        existing_metas = []
        if append and self.meta_path.exists():
            existing_metas = json.load(open(self.meta_path, "r", encoding="utf-8"))
            print(f"  追加模式：现有 {len(existing_metas)} 条", flush=True)

        # Embedding
        texts = [c["text"] for c in chunks]
        print(f"  生成 embedding（{len(texts)} 条）...", flush=True)
        embeddings = self.model.encode(
            texts, normalize_embeddings=True,  # L2 归一化（配合内积相似度）
            show_progress_bar=True,
        )
        embeddings = np.ascontiguousarray(embeddings, dtype="float32")
        print(f"  embedding 维度: {embeddings.shape}", flush=True)

        # 合并已有向量
        if existing_metas and append and self.index_path.exists():
            old_index = faiss.read_index(str(self.index_path))
            old_vecs = faiss.rev_swig_ptr(
                old_index.get_xb(), old_index.ntotal * old_index.d
            ).reshape(old_index.ntotal, old_index.d)
            embeddings = np.ascontiguousarray(
                np.vstack([old_vecs, embeddings]), dtype="float32"
            )
            all_metas = existing_metas + chunks
        else:
            all_metas = chunks

        # 建 FAISS 索引（内积，因为已归一化 = 余弦相似度）
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        print(f"  FAISS 索引: {index.ntotal} 条, {dim} 维", flush=True)

        # 保存
        faiss.write_index(index, str(self.index_path))
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(all_metas, f, ensure_ascii=False, indent=2)

        print(f"  ✅ 保存: {self.index_path.name} + {self.meta_path.name}",
              flush=True)
        return len(all_metas)

    # ============================================================
    # 检索
    # ============================================================
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """检索最相关的 top_k 条记忆。

        Returns:
            [{"text", "center_text", "rec", "file", "start", "end",
              "speaker", "emotion", "score"}, ...]
        """
        if self._index is None:
            self._load()

        if self._index is None or self._index.ntotal == 0:
            return []

        import numpy as np

        # query embedding
        qvec = self.model.encode(
            [query], normalize_embeddings=True,
        )
        qvec = np.ascontiguousarray(qvec, dtype="float32")

        # 搜索
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(qvec, k)

        results = []
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0])):
            if idx < 0:
                continue
            meta = self._metas[idx].copy()
            meta["score"] = float(score)
            meta["rank"] = rank + 1
            results.append(meta)
        return results

    # ============================================================
    # 持久化
    # ============================================================
    def _load(self):
        """加载 FAISS index 和元数据"""
        import faiss
        if self.index_path.exists() and self.meta_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            self._metas = json.load(open(self.meta_path, "r", encoding="utf-8"))
            print(f"  ✅ 加载记忆库: {self._index.ntotal} 条", flush=True)
        else:
            self._index = None
            self._metas = []
            print(f"  ⚠️ 记忆库不存在: {self.index_path}", flush=True)

    def stats(self) -> dict:
        """返回库的统计信息"""
        if self._index is None:
            self._load()
        return {
            "total": self._index.ntotal if self._index else 0,
            "index_path": str(self.index_path),
            "meta_path": str(self.meta_path),
            "model": self.model_name,
        }
