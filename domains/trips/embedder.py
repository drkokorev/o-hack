"""Эмбеддинги предложений multilingual-e5-small — локально, на процессоре, без сети.

Модель (ONNX int8, MIT) лежит в domains/trips/models/e5_small двумя частями по ≤60 МБ — лимит GitHub
на файл; части склеиваются в памяти и сверяются с контрольной суммой из manifest.json. Вопрос кодируется
за единицы миллисекунд; векторы фрагментов путеводителей посчитаны заранее (tools/build_guides.py --vectors).
Если модели или onnxruntime нет, available() возвращает False и поиск работает без неё.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)
MODEL_DIR = Path(__file__).parent / "models" / "e5_small"
MAX_TOKENS = 512
_LOCK = threading.Lock()


_LOAD = threading.Lock()


def _load():
    with _LOAD:
        return _load_once()


@lru_cache(maxsize=1)
def _load_once():
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
    except ImportError:
        return None
    manifest_path = MODEL_DIR / "manifest.json"
    parts = sorted(MODEL_DIR.glob("model_int8.onnx.part-*"))
    if not manifest_path.exists() or not parts:
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = b"".join(part.read_bytes() for part in parts)
    tokenizer_path = MODEL_DIR / "tokenizer.json"
    if (hashlib.sha256(model).hexdigest() != manifest["model_sha256"] or
            hashlib.sha256(tokenizer_path.read_bytes()).hexdigest() != manifest["tokenizer_sha256"]):
        log.warning("Модель эмбеддингов повреждена (контрольная сумма), поиск идёт без неё")
        return None
    if hasattr(ort, "disable_telemetry_events"):
        ort.disable_telemetry_events()  # никаких событий наружу и шума в логах
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(model, sess_options=options, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(MAX_TOKENS)
    tokenizer.enable_padding()
    return session, tokenizer, {i.name for i in session.get_inputs()}


def available() -> bool:
    return _load() is not None


def encode(texts: list[str], kind: str = "query", batch: int = 32) -> np.ndarray | None:
    """Нормированные векторы 384; kind — «query» для вопроса, «passage» для фрагмента (так обучена e5)."""
    loaded = _load()
    if loaded is None or not texts:
        return None
    session, tokenizer, inputs = loaded
    out = []
    for start in range(0, len(texts), batch):
        encoded = tokenizer.encode_batch([f"{kind}: {t}" for t in texts[start:start + batch]])
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        with _LOCK:
            hidden = np.asarray(session.run(None, feed)[0])
        pooled = (hidden * mask[..., None]).sum(axis=1) / mask.sum(axis=1, keepdims=True)
        out.append(pooled / np.linalg.norm(pooled, axis=1, keepdims=True))
    return np.vstack(out).astype(np.float32)
