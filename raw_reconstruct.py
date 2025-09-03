#!/usr/bin/env python3
"""
raw_reconstruct.py

Восстанавливает field.raw из extracted/fragment + metadata.json.
Поднимает лимит на длину числа при необходимости.
"""

import sys

# поднимаем лимит для длинных чисел при JSON-парсинге
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(30000)

import json
import re
from pathlib import Path

FRAG_SIZE = 128


def inverse_transform(data: bytes, ops):
    for op in reversed(ops):
        if op == "identity":
            continue
        elif op == "invert":
            data = bytes((~b & 0xFF) for b in data)
        elif op == "xor":
            data = bytes((b ^ 0xFF) for b in data)
        else:
            raise ValueError(f"Unknown transform: {op}")
    return data


def reconstruct_raw(fragments_dir: Path, meta_path: Path, out_path: Path):
    if not meta_path.exists():
        fallback = Path("pipeline_output/metadata.auto.json")
        if fallback.exists():
            print(f"[!] metadata не найден, используем {fallback}", file=sys.stderr)
            meta_path = fallback
        else:
            sys.exit(f"[ERROR] metadata.json не найден: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    max_end = 0
    for entry in meta.values():
        off = entry.get("offset") or 0
        max_end = max(max_end, off + FRAG_SIZE)

    buffer = bytearray(max_end)
    filled = bytearray(max_end)

    for fname, entry in meta.items():
        offset = entry.get("offset") or 0
        ops    = entry.get("transform_chain", ["identity"])
        wave   = entry.get("wave")
        frag   = fragments_dir / f"wave_{wave}" / fname
        if not frag.exists():
            continue

        data = frag.read_bytes()
        orig = inverse_transform(data, ops)
        for i, b in enumerate(orig):
            pos = offset + i
            if pos < len(buffer) and filled[pos] == 0:
                buffer[pos] = b
                filled[pos] = 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buffer)
    print(f"[+] Recovered raw → {out_path} (coverage {filled.count(1)}/{len(buffer)})")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(__doc__)
    p.add_argument("-d", "--fragments-dir", default="extracted")
    p.add_argument("-m", "--metadata",      default="extracted/metadata.json")
    p.add_argument("-o", "--output",        default="recovered_field.raw")
    args = p.parse_args()

    reconstruct_raw(
        Path(args.fragments_dir),
        Path(args.metadata),
        Path(args.output)
    )
