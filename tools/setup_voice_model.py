"""Fetch a pinned optional GigaAM ONNX snapshot outside the repository."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from huggingface_hub import snapshot_download

from apps.voice import MODEL_REVISION

FILES = {
    "v3_e2e_ctc.int8.onnx": "2e3fcb7a7b66030336fd10c2fcfb033bd1dc7e1bf238fe5cfd83b1d0cfc9d28e",
    "v3_e2e_ctc_vocab.txt": "142de7570b3de5b3035ce111a89c228e80e6085273731d944093ddf24fa539cd",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path, help="Directory outside Git for the model files")
    args = parser.parse_args()
    target = args.output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if target == repo or repo in target.parents:
        raise ValueError("Model files must be kept outside the Git working tree")
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download("istupakov/gigaam-v3-onnx", revision=MODEL_REVISION, token=False, local_dir=target,
                      allow_patterns=[*FILES, "v3_e2e_ctc.yaml"])
    for name, expected in FILES.items():
        digest = hashlib.sha256()
        with (target / name).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"Invalid checksum: {name}")
    print(f"GigaAM model ready: {target}")


if __name__ == "__main__":
    main()
