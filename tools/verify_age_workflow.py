"""Проверить инструкцию age на вымышленных данных, не читая ключи проекта.

Нужны официальные программы age и age-keygen в PATH или --age-dir.
Программа не создаёт файл для сдачи и не обращается к реальному .env.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ORGANIZER_RECIPIENT = "age1932fu7f70rwyfhaxflyfszz4gf6avxwc95wc0yjwm6zns9tspycqpgdnc0"
FIXTURE = b"LLM_PROVIDER=example\nLLM_API_KEY=not-a-real-key\n"


def executable(name: str, directory: str | None) -> str:
    if directory:
        candidate = Path(directory) / (name + ".exe" if os.name == "nt" else name)
        if candidate.is_file():
            return str(candidate.resolve())
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Не найдена программа {name}; установите age или укажите --age-dir")
    return found


def invoke(args: list[str], label: str, *, expect_success: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, check=False)
    if (result.returncode == 0) != expect_success:
        raise RuntimeError(f"Не прошла проверка: {label} (код {result.returncode})")
    return result


def verify(age: str, keygen: str, recipient: str) -> None:
    if not re.fullmatch(r"age1[0-9a-z]+", recipient):
        raise ValueError("Некорректный формат публичного ключа организаторов")
    base = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(prefix="o-hack-age-", dir=base) as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(base):
            raise RuntimeError("Временный каталог расположен вне ожидаемой папки")
        source, identity = root / "sample.env", root / "local-identity.txt"
        jury_encrypted, test_encrypted, restored = root / "jury.age", root / "local.age", root / "restored.env"
        source.write_bytes(FIXTURE)
        invoke([keygen, "-o", str(identity)], "создание временного тестового ключа")
        public = invoke([keygen, "-y", str(identity)], "чтение временного публичного ключа").stdout.decode("ascii").strip()
        invoke([age, "-r", recipient, "-o", str(jury_encrypted), str(source)], "шифрование получателю организаторов")
        blob = jury_encrypted.read_bytes()
        if not blob.startswith(b"age-encryption.org/v1\n") or FIXTURE in blob:
            raise RuntimeError("Результат не похож на бинарный age-файл или содержит открытый образец")
        invoke([age, "-d", "-i", str(identity), "-o", str(restored), str(jury_encrypted)],
               "проверка, что случайный ключ не подходит получателю организаторов", expect_success=False)
        invoke([age, "-r", public, "-o", str(test_encrypted), str(source)], "шифрование тестовому получателю")
        invoke([age, "-d", "-i", str(identity), "-o", str(restored), str(test_encrypted)], "расшифровка тестовым получателем")
        if restored.read_bytes() != FIXTURE:
            raise RuntimeError("Расшифрованный тестовый образец отличается от исходного")
    print("PASS: формат age, тест шифрования/расшифровки и защита от чужого ключа")
    print("Организаторский файл зашифрован на вымышленных данных; расшифровка организаторами не проверялась.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--age-dir", help="Каталог с age и age-keygen, если они не в PATH")
    parser.add_argument("--recipient", default=ORGANIZER_RECIPIENT, help="Публичный ключ из актуальной инструкции организаторов")
    args = parser.parse_args()
    verify(executable("age", args.age_dir), executable("age-keygen", args.age_dir), args.recipient)


if __name__ == "__main__":
    main()
