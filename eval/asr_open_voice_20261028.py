"""Small real-speech smoke test. Fetch public samples in memory; do not save audio or transcripts."""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import time
import urllib.request
from pathlib import Path

import onnx_asr
import soundfile as sf
from huggingface_hub import snapshot_download

DATASET = "bond005/sova_rudevices"
DATASET_REV = "d9197eacfb0afff29d90a2d4e7d0d98a5dfb54bc"
MODEL = "gigaam-v3-e2e-ctc"
MODEL_REV = "322c3b29492673eb7d0b434bfa9dfb8653e34d02"


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, item in enumerate(reference, 1):
        old, row[0] = row[0], i
        for j, other in enumerate(hypothesis, 1):
            old, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, old + (item != other))
    return row[-1]


def words(text: str) -> list[str]:
    return re.sub(r"[^а-яa-z0-9 ]", " ", text.lower().replace("ё", "е")).split()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()
    started = time.monotonic()
    model_dir = snapshot_download("istupakov/gigaam-v3-onnx", revision=MODEL_REV, token=False,
                                  allow_patterns=["v3_e2e_ctc.int8.onnx", "v3_e2e_ctc.yaml", "v3_e2e_ctc_vocab.txt"])
    model = onnx_asr.load_model(MODEL, model_dir, quantization="int8")
    load_seconds = time.monotonic() - started
    url = ("https://datasets-server.huggingface.co/first-rows?dataset=bond005%2Fsova_rudevices"
           "&config=default&split=test")
    with urllib.request.urlopen(url, timeout=30) as response:
        rows = json.load(response)["rows"][:args.count]
    failures, errors, total, times, durations = [], 0, 0, [], []
    for item in rows:
        index, row = item["row_idx"], item["row"]
        try:
            audio = row["audio"][0] if isinstance(row["audio"], list) else row["audio"]
            with urllib.request.urlopen(audio["src"], timeout=30) as response:
                wave, sample_rate = sf.read(io.BytesIO(response.read()), dtype="float32")
            duration = len(wave) / sample_rate
            t = time.monotonic()
            hypothesis = model.recognize(wave, sample_rate=sample_rate)
            times.append(time.monotonic() - t)
            durations.append(duration)
            reference_words, hypothesis_words = words(row["transcription"]), words(hypothesis)
            errors += edit_distance(reference_words, hypothesis_words)
            total += len(reference_words)
            print(f"row {index}: processed", flush=True)
        except Exception as exc:
            failures.append({"index": index, "error_type": type(exc).__name__})
            print(f"row {index}: {type(exc).__name__}", flush=True)
    report = {"model": MODEL, "model_revision": MODEL_REV, "quantization": "int8", "dataset": DATASET,
              "dataset_revision": DATASET_REV, "dataset_license": "CC BY 4.0", "split": "test",
              "selection": f"first {args.count} rows", "requested": args.count, "processed": len(times),
              "failed": failures, "speaker_count": "unknown", "word_errors": errors,
              "reference_words": total, "wer": round(errors / total, 4) if total else None,
              "latency_median_s": round(statistics.median(times), 3) if times else None,
              "audio_seconds": round(sum(durations), 3), "load_seconds": round(load_seconds, 3),
              "limitations": "Small convenience sample; no speaker labels; domain differs from travel; dataset may be represented in upstream evaluation/training."}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if len(times) == args.count and total else 1


if __name__ == "__main__":
    raise SystemExit(main())
