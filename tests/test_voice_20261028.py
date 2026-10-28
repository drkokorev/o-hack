import io
import wave

from fastapi.testclient import TestClient

from apps.voice import MAX_AUDIO_BYTES, LocalVoice, validate_wav
from apps.web import build_app


def wav(seconds=1, rate=16000, channels=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as sound:
        sound.setnchannels(channels)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(b"\0\0" * rate * seconds * channels)
    return out.getvalue()


def test_rules_mode_uses_browser_voice_when_no_local_model_is_set(monkeypatch):
    monkeypatch.delenv("VOICE_MODEL_DIR", raising=False)
    with TestClient(build_app()) as client:
        assert client.get("/api/voice").json() == {"backend": "browser", "status": "off", "max_seconds": 20}
        assert client.post("/api/voice/transcribe", content=wav()).status_code == 503


def test_audio_route_validates_and_does_not_send_chat(monkeypatch):
    class FakeVoice(LocalVoice):
        def load(self):
            self.status = "ready"

        def transcribe(self, raw):
            pcm, rate = validate_wav(raw)
            assert rate == 16000 and len(pcm) == 32000
            return "хочу в горы"

    monkeypatch.setenv("VOICE_MODEL_DIR", "test-only")
    monkeypatch.setattr("apps.web.LocalVoice", FakeVoice)
    with TestClient(build_app()) as client:
        response = client.post("/api/voice/transcribe", content=wav(), headers={"Content-Type": "audio/wav"})
        assert response.status_code == 200 and response.json() == {"text": "хочу в горы", "backend": "gigaam"}
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/api/voice/transcribe", content=b"not wav").status_code == 400
        assert client.post("/api/voice/transcribe", content=wav(rate=8000)).status_code == 400
        assert client.post("/api/voice/transcribe", content=wav(seconds=21)).status_code == 400
        assert client.post("/api/voice/transcribe", content=b"x" * (MAX_AUDIO_BYTES + 1)).status_code == 413
