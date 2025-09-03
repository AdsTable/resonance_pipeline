## https://copilot.microsoft.com/shares/kETii6YGcvnHPQq2RkJey

# Полный пошаговый гайд с кодом и примерами запуска
Ниже описан полный набор файлов, их назначение, содержимое и команды для запуска. Цель конвейера:

Преобразовать JSON-массив байтов в бинарный файл field.raw

Разрезать field.raw на фрагменты с трансформациями и записать реальные seed-хеши в metadata.json

Собрать метрики, выполнить batch-анализ и кластеризацию

Построить чистый граф seed → fragment + опциональный шум

Экспортировать граф в PNG и GraphML

Проанализировать топологию и сохранить статистику

При необходимости восстановить исходный field.raw из фрагментов

Весь код сохраняйте в папке проекта (например, resonance_pipeline/), файлы — в UTF-8 без BOM.

1. array_to_raw.py
Конвертирует JSON-массив (или одно большое целое) в бинарный field.raw.

python
#!/usr/bin/env python3
"""
array_to_raw.py

Читает JSON-файл с массивом байтов или одним большим целым
и записывает бинарный файл field.raw.
"""

import sys, json, argparse
from pathlib import Path

# Для Python 3.11+: повышаем лимит на длинные int-строки
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

def array_to_raw(input_json: Path, output_raw: Path):
    text = input_json.read_text(encoding="utf-8")
    parsed = json.loads(text)

    if isinstance(parsed, int):
        length = max((parsed.bit_length() + 7) // 8, 1)
        data = parsed.to_bytes(length, byteorder="big")
    elif isinstance(parsed, list):
        data = bytes(parsed)
    else:
        raise ValueError(f"Unsupported JSON type: {type(parsed)}")

    output_raw.parent.mkdir(parents=True, exist_ok=True)
    output_raw.write_bytes(data)
    print(f"[+] Wrote raw file: {output_raw} ({len(data)} bytes)")

if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("-i", "--input-json",
                   default="data_array.json",
                   help="Input JSON of ints or big-int")
    p.add_argument("-o", "--output-raw",
                   default="field.raw",
                   help="Output raw file path")
    args = p.parse_args()
    array_to_raw(Path(args.input_json), Path(args.output_raw))
Запуск:

bash
python array_to_raw.py \
  -i data_array.json \
  -o field.raw
2. resonant_extract.py
Нарезает field.raw на фрагменты, применяет трансформации, сохраняет extracted/metadata.json с реальными SHA-seed.

python
#!/usr/bin/env python3
"""
resonant_extract.py

Нарезает field.raw на фрагменты по 128 байт с identity/invert/xor
и генерирует metadata.json с полем "seed" = SHA256 первых 16 байт.
"""

import sys, json, hashlib, argparse
from pathlib import Path

# Параметры
WAVES           = 5
PULSES_PER_WAVE = 10
SEED_SIZE       = 16
FRAG_SIZE       = 128
EXTRACT_DIR     = Path("extracted")
META_FILE       = EXTRACT_DIR / "metadata.json"

def load_meta():
    return json.loads(META_FILE.read_text(encoding="utf-8")) if META_FILE.exists() else {}

def save_meta(meta):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]

def transformations(fragment: bytes):
    yield "identity", fragment
    yield "invert", bytes(~b & 0xFF for b in fragment)
    yield "xor",    bytes(b ^ 0xFF for b in fragment)

def extract_fragments(raw_file: str):
    raw_path = Path(raw_file)
    if not raw_path.exists():
        print(f"[!] Raw '{raw_file}' not found, skipping.", file=sys.stderr)
        return

    buf = raw_path.read_bytes()
    meta = load_meta()

    for wave in range(WAVES):
        seed_off   = wave * FRAG_SIZE
        seed_id    = hash_bytes(buf[seed_off: seed_off + SEED_SIZE])

        for pulse in range(PULSES_PER_WAVE):
            offset = wave*FRAG_SIZE + pulse*(SEED_SIZE//2)
            frag   = buf[offset: offset + FRAG_SIZE]
            for op, data in transformations(frag):
                name = f"w{wave}_p{pulse}_{offset}_{op}.bin"
                dir_wave = EXTRACT_DIR / f"wave_{wave}"
                dir_wave.mkdir(parents=True, exist_ok=True)
                (dir_wave / name).write_bytes(data)

                hd    = sum(a!=b for a,b in zip(frag, data))
                score = round(1 - hd/FRAG_SIZE, 4)
                meta[name] = {
                    "wave": wave,
                    "seed": seed_id,
                    "offset": offset,
                    "pulse_index": pulse,
                    "transform_chain": [op],
                    "hamming_distance": hd,
                    "detection_score": score
                }
                save_meta(meta)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("raw_file", help="Path to field.raw")
    args = parser.parse_args()
    extract_fragments(args.raw_file)
Запуск:

bash
python resonant_extract.py field.raw
3. config.yaml
Конфигурация конвейера:

yaml
raw_file: "field.raw"
fragments_dir: "extracted"
metadata_file: "extracted/metadata.json"
output_dir: "pipeline_output"
jobs: 8

plot_dir: "plots"
batch_results: "batch.json"
cluster_csv: "clusters.csv"
graph_image: "graph.png"
graphml: "resonance.graphml"

node_attrs:
  - size
  - entropy
  - wave
  - offset
  - pulse_index

edge_attrs:
  - hamming_distance
  - transform_chain
  - detection_score

color_by: "detection_score"

x_col: "wave"
y_col: "size"
hue_col: "entropy"

connect_clusters: true
fallback_random_seeds_count: 3
add_cycle: true
echo_enabled: true
4. pipeline.py
Оркестратор: метрики → batch → кластер → граф → анализ.

python
#!/usr/bin/env python3
"""
pipeline.py

Главный скрипт: собирает метрики, кластеризует, строит граф и анализирует.
"""

import sys, yaml, logging, argparse
from pathlib import Path

from metrics_collector import collect_metrics, plot_metrics
from batch_analysis    import batch_analyze, save_results
from cluster_resonance import load_batch_results, cluster_and_select
from graph_export      import (
    synthesize_metadata,
    build_graph,
    visualize_graph,
    export_graphml
)
from graph_analysis    import analyze_graph

# Подними лимит для длинных int
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

def setup_logging():
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    return logging.getLogger("pipeline")

def load_config(path, logger):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    required = [
        "raw_file","fragments_dir","metadata_file","output_dir","jobs",
        "plot_dir","batch_results","cluster_csv","graph_image","graphml",
        "node_attrs","edge_attrs","color_by",
        "x_col","y_col","hue_col",
        "connect_clusters","fallback_random_seeds_count",
        "add_cycle","echo_enabled"
    ]
    miss = [k for k in required if k not in cfg]
    if miss: logger.error("Missing config: %s", miss); sys.exit(1)
    return cfg

def ensure_parent(p: Path): p.parent.mkdir(parents=True, exist_ok=True)

def guess_column(df, pref, logger):
    if pref in df.columns: return pref
    nums = [c for c in df.columns if df[c].dtype.kind in ("i","u","f")]
    fb = nums[0] if nums else None
    logger.warning("'%s' not found, use '%s'", pref, fb)
    return fb

def main():
    logger = setup_logging()
    p = argparse.ArgumentParser()
    p.add_argument("--config","-c",default="config.yaml")
    args = p.parse_args()

    cfg = load_config(args.config, logger)
    frags = Path(cfg["fragments_dir"])
    meta  = Path(cfg["metadata_file"])
    out   = Path(cfg["output_dir"]); out.mkdir(exist_ok=True)

    # 1) Extract fragments
    from resonant_extract import extract_fragments
    extract_fragments(cfg["raw_file"])

    # 1.5) Auto-gen metadata if missing
    if not meta.exists():
        meta = synthesize_metadata(frags, out/"metadata.auto.json", logger)

    # 2) Metrics + plots
    df = collect_metrics(str(frags), str(meta))
    logger.info("Metrics collected: %d", len(df))
    if not df.empty:
        x = guess_column(df, cfg["x_col"], logger)
        y = guess_column(df, cfg["y_col"], logger)
        h = cfg["hue_col"] if cfg["hue_col"] in df.columns else None
        plot_metrics(df, str(out/cfg["plot_dir"]), x_col=x, y_col=y, hue_col=h)

    # 3) Batch-analysis
    batch = batch_analyze(str(frags), jobs=cfg["jobs"])
    ensure_parent(out/cfg["batch_results"])
    save_results(batch, str(out/cfg["batch_results"]))

    # 4) Clustering
    dfb = load_batch_results(str(out/cfg["batch_results"]))
    dfc, seeds = cluster_and_select(dfb)
    ensure_parent(out/cfg["cluster_csv"])
    dfc.to_csv(out/cfg["cluster_csv"], index=False)

    # 5) Build and export graph
    G = build_graph(
        meta,
        out/cfg["batch_results"],
        frags,
        cfg["node_attrs"],
        cfg["edge_attrs"],
        cfg["color_by"],
        cfg["connect_clusters"],
        cfg["fallback_random_seeds_count"],
        cfg["add_cycle"],
        cfg["echo_enabled"],
        logger
    )
    G.graph["cluster_seeds"] = seeds
    visualize_graph(G, str(out/cfg["graph_image"]), cfg["color_by"])
    export_graphml(G, str(out/cfg["graphml"]))

    # 6) Graph analysis
    stats = analyze_graph(G, out)
    logger.info("Graph stats: %s", stats)

if __name__ == "__main__":
    main()
Запуск:

bash
python pipeline.py --config config.yaml
5. graph_export.py
Сборка графа, визуализация, экспорт в PNG и GraphML. (См. подробный код выше в шаге 4 конвейера.)

6. graph_analysis.py
Сбор топологических метрик и гистограмма степеней. (См. подробный код выше в шаге 4 конвейера.)

7. raw_reconstruct.py
Восстанавливает field.raw из папки extracted/ и metadata.json.

python
#!/usr/bin/env python3
import sys, json
from pathlib import Path

FRAG_SIZE = 128

# Поднимаем лимит для больших int, если нужно
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

def inverse_transform(data, ops):
    for op in reversed(ops):
        if op=="invert": data = bytes(~b & 0xFF for b in data)
        elif op=="xor":  data = bytes(b ^ 0xFF for b in data)
    return data

def reconstruct_raw(frag_dir: Path, meta_file: Path, out_file: Path):
    meta = json.loads(meta_file.read_text())
    max_end = max(m["offset"]+FRAG_SIZE for m in meta.values())
    buf = bytearray(max_end)
    filled = bytearray(max_end)

    for fn,m in meta.items():
        path = frag_dir / f"wave_{m['wave']}" / fn
        if not path.exists(): continue
        data = inverse_transform(path.read_bytes(), m["transform_chain"])
        for i,b in enumerate(data):
            pos = m["offset"] + i
            if not filled[pos]:
                buf[pos] = b
                filled[pos] = 1

    out_file.write_bytes(buf)
    print(f"[+] Recovered raw → {out_file}, coverage {filled.count(1)}/{len(buf)}")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("-d","--fragments-dir",default="extracted")
    p.add_argument("-m","--metadata",     default="extracted/metadata.json")
    p.add_argument("-o","--output",       default="recovered_field.raw")
    args=p.parse_args()
    reconstruct_raw(Path(args.fragments_dir), Path(args.metadata), Path(args.output))
Запуск:

bash
python raw_reconstruct.py \
  -d extracted \
  -m extracted/metadata.json \
  -o recovered_field.raw
Резюме команд
bash
# 1) JSON → raw
python array_to_raw.py -i data_array.json -o field.raw

# 2) raw → fragments + metadata
python resonant_extract.py field.raw

# 3) полный анализ и graph
python pipeline.py --config config.yaml

# 4) восстановление raw (опционально)
python raw_reconstruct.py -d extracted -m extracted/metadata.json -o recovered_field.raw
Теперь у вас есть полный, развёрнутый набор скриптов с инструкцией запуска каждого шага.