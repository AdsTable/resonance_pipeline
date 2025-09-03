#!/usr/bin/env python3
"""
Orchestrator: extract → metrics → batch → cluster → graph → analysis.
Поднимаем лимит для длинных целых, чтобы не ловить ValueError(“Exceeds the limit”).
"""

import sys

# если Python ≥ 3.11 — поднимаем лимит на длину числа в str→int
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(30000)

import yaml
import logging
import argparse
from pathlib import Path

from metrics_collector    import collect_metrics, plot_metrics
from batch_analysis       import batch_analyze, save_results
from cluster_resonance    import load_batch_results, cluster_and_select
from graph_export         import (
    synthesize_metadata,
    build_graph,
    visualize_graph,
    export_graphml
)
from graph_analysis       import analyze_graph


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    return logging.getLogger("pipeline")


def load_config(path, logger):
    path = Path(path)
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.error("Не удалось прочитать конфиг '%s': %s", path, e)
        sys.exit(1)
    required = [
        "raw_file","fragments_dir","metadata_file","output_dir","jobs",
        "plot_dir","batch_results","cluster_csv","graph_image","graphml",
        "node_attrs","edge_attrs","color_by",
        "x_col","y_col","hue_col",
        "connect_clusters","fallback_random_seeds_count",
        "add_cycle","echo_enabled"
    ]
    missing = [k for k in required if k not in cfg]
    if missing:
        logger.error("В конфиге отсутствуют поля: %s", missing)
        sys.exit(1)
    return cfg


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def guess_column(df, pref, logger):
    if pref in df.columns:
        return pref
    nums = [c for c in df.columns if df[c].dtype.kind in ("i", "u", "f")]
    fallback = nums[0] if nums else None
    logger.warning("Колонка '%s' не найдена, берём '%s'", pref, fallback)
    return fallback


def main():
    logger = setup_logging()

    p = argparse.ArgumentParser("Resonance Pipeline")
    p.add_argument("--config","-c", default="config.yaml", help="YAML config file")
    args = p.parse_args()

    cfg       = load_config(args.config, logger)
    raw_file  = cfg["raw_file"]
    frags_dir = Path(cfg["fragments_dir"])
    meta_file = Path(cfg["metadata_file"])
    out_dir   = Path(cfg["output_dir"])
    jobs      = int(cfg["jobs"])
    node_attrs= cfg["node_attrs"]
    edge_attrs= cfg["edge_attrs"]
    color_by  = cfg["color_by"]

    plot_dir     = out_dir / cfg["plot_dir"]
    batch_path   = out_dir / cfg["batch_results"]
    cluster_path = out_dir / cfg["cluster_csv"]
    graph_img    = out_dir / cfg["graph_image"]
    graphml_path = out_dir / cfg["graphml"]

    out_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # 0) extract fragments, если raw_file задан
    if raw_file:
        rf = Path(raw_file)
        if rf.exists():
            from resonant_extract import extract_fragments
            extract_fragments(raw_file)
        else:
            logger.warning("Raw-файл '%s' не найден — пропускаем extract", raw_file)

    # 0.5) synthesize metadata, если его нет
    if not meta_file.exists():
        auto_meta = out_dir / "metadata.auto.json"
        meta_file = synthesize_metadata(frags_dir, auto_meta, logger)

    # 1) Метрики + графики
    df = collect_metrics(str(frags_dir), str(meta_file))
    logger.info("Метрик собрано: %d", len(df))

    if not df.empty:
        x_col   = guess_column(df, cfg["x_col"], logger)
        y_col   = guess_column(df, cfg["y_col"], logger)
        hue_col = cfg["hue_col"] if cfg["hue_col"] in df.columns else None

        plot_metrics(df, str(plot_dir),
                     x_col=x_col, y_col=y_col, hue_col=hue_col)
        logger.info("Графики сохранены в %s", plot_dir)
    else:
        logger.warning("Нет данных для графиков, пропускаем")

    # 2) Batch-анализ
    batch = batch_analyze(str(frags_dir), jobs=jobs)
    ensure_parent(batch_path)
    save_results(batch, str(batch_path))
    logger.info("Batch-анализ сохранён: %s", batch_path)

    # 3) Кластеризация
    df_batch = load_batch_results(str(batch_path))
    df_clust, seeds = cluster_and_select(df_batch)
    ensure_parent(cluster_path)
    df_clust.to_csv(cluster_path, index=False)
    logger.info("Кластеры сохранены: %s", cluster_path)
    logger.info("New seeds: %s", seeds or "none")

    # 4) Построение и экспорт графа
    G = build_graph(
        meta_file,
        batch_path,
        frags_dir,
        node_attrs,
        edge_attrs,
        color_by,
        cfg["connect_clusters"],
        cfg["fallback_random_seeds_count"],
        cfg["add_cycle"],
        cfg["echo_enabled"],
        logger
    )
    G.graph["cluster_seeds"] = seeds

    if G.number_of_nodes() == 0:
        logger.warning("Граф пуст — выходим")
        return

    visualize_graph(G, str(graph_img), color_by)
    export_graphml(G, str(graphml_path))
    logger.info("Граф сохранён: %s и %s", graph_img, graphml_path)

    # 5) Анализ графа
    stats = analyze_graph(G, out_dir)
    logger.info(
        "Graph stats: Nodes=%d Edges=%d Comps=%d Largest=%d",
        stats["num_nodes"], stats["num_edges"],
        stats["num_components"], stats["largest_component_size"]
    )


if __name__ == "__main__":
    main()
