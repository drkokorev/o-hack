"""Optional local speech-to-text; no audio or transcript is written to disk."""
from __future__ import annotations

import io
import logging
import threading
import wave
from pathlib import Path

log = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 2_000_000
MAX_AUDIO_SECONDS = 20
MODEL_NAME = "gigaam-v3-e2e-ctc"
MODEL_REVISION = "322c3b29492673eb7d0b434bfa9dfb8653e34d02"


def validate_wav(raw: bytes) -> tuple[bytes, int]:
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise ValueError("Слишком большой или пустой аудиофайл")
    try:
        with wave.open(io.BytesIO(raw), "rb") as sound:
            rate, channels, width, frames = sound.getframerate(), sound.getnchannels(), sound.getsampwidth(), sound.getnframes()
            if channels != 1 or width != 2 or rate != 16000 or not 0 < frames <= rate * MAX_AUDIO_SECONDS:
                raise ValueError("Нужен одноканальный PCM 16 кГц длительностью до 20 секунд")
            audio = sound.readframes(frames)
            if len(audio) != frames * width:
                raise ValueError("Аудиофайл повреждён")
            return audio, rate
    except (wave.Error, EOFError) as exc:
        raise ValueError("Ожидается корректный WAV") from exc


class LocalVoice:
    def __init__(self, model_dir: str | None):
        self.model_dir = Path(model_dir) if model_dir else None
        self.model = None
        self.status = "off" if self.model_dir is None else "loading"
        self._lock = threading.Lock()

    def load(self) -> None:
        if self.model_dir is None:
            return
        try:
            import onnx_asr
            import onnxruntime

            if not self.model_dir.is_dir():
                raise FileNotFoundError("voice model directory is absent")
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            options.add_session_config_entry("session.inter_op.allow_spinning", "0")
            self.model = onnx_asr.load_model(MODEL_NAME, self.model_dir, quantization="int8", sess_options=options)
            self.status = "ready"
        except Exception as exc:
            self.status = "unavailable"
            # Avoid exposing audio, credentials or local paths in logs.
            log.warning("Local speech model unavailable: %s", type(exc).__name__)

    def transcribe(self, raw: bytes) -> str:
        audio, rate = validate_wav(raw)
        if self.model is None:
            raise RuntimeError("Голосовая модель ещё не готова")
        import numpy as np

        samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
        with self._lock:
            return str(self.model.recognize(samples, sample_rate=rate)).strip()
