#!/usr/bin/env python3
"""
resonant_extract.py

Нарезает field.raw на фрагменты, применяет трансформации
и сохраняет metadata.json с полем "seed" = SHA256 первых 16 байт блока.
"""

import sys, json, hashlib, argparse
from pathlib import Path

WAVES           = 5
PULSES_PER_WAVE = 10
SEED_SIZE       = 16
FRAG_SIZE       = 128

EXTRACT_DIR = Path("extracted")
META_FILE   = EXTRACT_DIR / "metadata.json"

def load_meta() -> dict:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return {}

def save_meta(meta: dict):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]

def transformations(fragment: bytes):
    yield ("identity", fragment)
    yield ("invert", bytes((~b & 0xFF) for b in fragment))
    yield ("xor",    bytes((b ^ 0xFF) for b in fragment))

def extract_fragments(raw_file: str):
    raw = Path(raw_file)
    if not raw.exists():
        print(f"[!] Raw file '{raw_file}' not found, skipping extract.", file=sys.stderr)
        return
    buf = raw.read_bytes()
    meta = load_meta()

    for wave in range(WAVES):
        seed_off   = wave * FRAG_SIZE
        seed_bytes = buf[seed_off: seed_off + SEED_SIZE]
        seed_id    = hash_bytes(seed_bytes)

        for pulse in range(PULSES_PER_WAVE):
            offset = wave * FRAG_SIZE + pulse * (SEED_SIZE // 2)
            frag   = buf[offset: offset + FRAG_SIZE]

            for op, data in transformations(frag):
                name = f"w{wave}_p{pulse}_{offset}_{op}.bin"
                odir = EXTRACT_DIR / f"wave_{wave}"
                odir.mkdir(parents=True, exist_ok=True)
                fpath = odir / name
                fpath.write_bytes(data)

                hd    = sum(a!=b for a,b in zip(frag, data))
                score = round(1 - hd/FRAG_SIZE, 4)

                meta[name] = {
                    "wave":             wave,
                    "seed":             seed_id,
                    "offset":           offset,
                    "pulse_index":      pulse,
                    "transform_chain":  [op],
                    "hamming_distance": hd,
                    "detection_score":  score
                }
                save_meta(meta)

if __name__=="__main__":
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("raw_file", help="Path to field.raw")
    args = p.parse_args()
    extract_fragments(args.raw_file)
