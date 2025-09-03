#!/usr/bin/env python3
"""
array_to_raw.py

Читает JSON-массив или большой JSON-инт и пишет бинарный файл field.raw.
Поднимает лимит на длину целых (Python 3.11+).
"""

import sys

# Python 3.11+ может ругаться на «слишком длинные» числа
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

import json
import argparse
from pathlib import Path

def array_to_raw(input_json: Path, output_raw: Path):
    # 1) Читаем любой JSON: list[int], int или hex-строку
    raw_text = input_json.read_text(encoding="utf-8")
    parsed   = json.loads(raw_text)

    # 2) В зависимости от типа – упаковываем в байты
    if isinstance(parsed, int):
        # большой целый → big-endian bytes
        n      = parsed
        length = max((n.bit_length() + 7) // 8, 1)
        data   = n.to_bytes(length, byteorder="big")
    elif isinstance(parsed, list):
        # список чисел
        data = bytes(parsed)
    elif isinstance(parsed, str):
        # строка: попробуем hex, иначе UTF-8
        try:
            # если строка – hex без префикса
            data = bytes.fromhex(parsed)
        except ValueError:
            data = parsed.encode("utf-8")
    else:
        raise ValueError(f"Unsupported JSON type: {type(parsed)}")

    # 3) Пишем файл
    output_raw.parent.mkdir(parents=True, exist_ok=True)
    output_raw.write_bytes(data)
    print(f"[+] Wrote raw file: {output_raw} ({len(data)} bytes)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "-i", "--input-json",
        default="data_array.json",
        help="JSON file containing either an int, a list of ints, or a hex string"
    )
    parser.add_argument(
        "-o", "--output-raw",
        default="field.raw",
        help="Path to write the reconstructed raw file"
    )
    args = parser.parse_args()
    array_to_raw(Path(args.input_json), Path(args.output_raw))
