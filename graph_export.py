#!/usr/bin/env python3
"""
graph_export.py

Сборка чистого графа real seed→fragment + опциональные шумовые фичи.
Теперь явно добавляем узлы для seed-хешей, чтобы ребра появлялись.
"""

import json
import uuid
import random
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path


def synthesize_metadata(fragments_dir: Path, out_meta: Path, logger) -> Path:
    logger.info("Автогенерация метаданных %s", out_meta)
    meta = {}
    for p in fragments_dir.rglob("*.bin"):
        # wave из папки wave_N
        wave = None
        if p.parent.name.startswith("wave_"):
            try:
                wave = int(p.parent.name.split("_", 1)[1])
            except ValueError:
                pass

        # offset: число перед .bin
        try:
            offset = int(p.name.split("_")[-2])
        except Exception:
            offset = None

        meta[p.name] = {
            "wave":             wave,
            "offset":           offset,
            "transform_chain": ["identity"]
        }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_meta


def build_graph(
    meta_json: Path,
    batch_json: Path,
    fragments_dir: Path,
    node_attrs: list,
    edge_attrs: list,
    color_by: str,
    connect_clusters: bool,
    fallback_random_seeds_count: int,
    add_cycle: bool,
    echo_enabled: bool,
    logger=None
) -> nx.DiGraph:
    G = nx.DiGraph()

    # 1) Узлы из batch.json
    if batch_json.exists():
        batch = json.loads(batch_json.read_text(encoding="utf-8"))
        for e in batch:
            fname = Path(e["path"]).name
            G.add_node(fname)
            for a in node_attrs:
                if a in e:
                    G.nodes[fname][a] = e[a]
    if logger:
        logger.info("Nodes from batch: %d", G.number_of_nodes())

    # 2) Meta-узлы + добавление seed-узлов
    metas = {}
    if meta_json.exists():
        metas = json.loads(meta_json.read_text(encoding="utf-8"))
    else:
        if logger:
            logger.warning("metadata.json not found: %s", meta_json)

    # сначала добавляем все fragment-узлы и их атрибуты
    for fname, m in metas.items():
        G.add_node(fname)
        for a in node_attrs:
            if a in m:
                G.nodes[fname][a] = m[a]

    # теперь добавляем все уникальные seed-узлы
    real_seeds = set()
    for m in metas.values():
        sd = m.get("seed")
        if sd:
            real_seeds.add(sd)
    for sd in real_seeds:
        G.add_node(sd)
        # помечаем узел как настоящий seed
        G.nodes[sd]["is_real_seed"] = True

    if logger:
        logger.info("Meta-nodes: %d, real seeds: %d", len(metas), len(real_seeds))

    # 3) Реальные seed→fragment рёбра
    cnt = 0
    for fname, m in metas.items():
        sd = m.get("seed")
        if sd and sd in G and fname in G:
            G.add_edge(sd, fname)
            for a in edge_attrs:
                if a in m:
                    G.edges[sd, fname][a] = m[a]
            cnt += 1
    if logger:
        logger.info("Seed→fragment edges: %d", cnt)

    # 4) Дополнительные «шумы», если включены
    # (connect_clusters, fallback, cycle, echo) — ваш прежний код
    # он сейчас не сработает при config:
    #   connect_clusters: false
    #   fallback_random_seeds_count: 0
    #   add_cycle: false
    #   echo_enabled: false

    if connect_clusters and "cluster_seeds" in G.graph:
        for s in G.graph["cluster_seeds"]:
            for fname, m in metas.items():
                if m.get("seed") == s:
                    G.add_edge(s, fname, cluster_link=True)
        if logger:
            logger.info("Cluster links added")

    # fallback seeds
    candidates = [
        n for n in G.nodes
        if n not in real_seeds
           and not n.startswith(("ph_", "rand_"))
           and n not in G.graph.get("cluster_seeds", [])
    ]
    random.shuffle(candidates)
    for rs in candidates[:fallback_random_seeds_count]:
        ph = f"rand_{uuid.uuid4().hex[:6]}"
        G.add_node(ph)
        G.add_edge(ph, rs, edge_type="random_fallback")
    if logger:
        logger.info("Random fallback seeds: %d", fallback_random_seeds_count)

    # placeholders
    for n in list(G.nodes):
        if n in real_seeds or G.in_degree(n) > 0:
            continue
        ph = f"ph_{uuid.uuid4().hex[:6]}"
        G.add_node(ph)
        G.add_edge(ph, n, edge_type="placeholder")
    if logger:
        logger.info("Placeholders added")

    # roots
    p1, p2 = "__primary_root__", "__secondary_root__"
    G.add_node(p1); G.add_node(p2)
    for s in real_seeds:
        G.add_edge(p1, s, edge_type="root_link")
    for n in list(G.nodes):
        if n not in real_seeds and n not in {p1, p2}:
            G.add_edge(p2, n, edge_type="root_link")
    if logger:
        logger.info("Roots connected")

    # cycle
    if add_cycle:
        chain = [n for n in G.nodes if n not in {p1, p2}]
        for i in range(len(chain)):
            G.add_edge(chain[i], chain[(i+1) % len(chain)], transform_chain=["cycle"])
        if logger:
            logger.info("Cycle added: %d links", len(chain))

    # echo
    if echo_enabled:
        count = 0
        for n in G.nodes:
            if not n.startswith("__"):
                en = f"echo_{n}"
                G.add_node(en)
                G.add_edge(n, en)
                count += 1
        if logger:
            logger.info("Echo edges added: %d", count)

    return G


def visualize_graph(G: nx.DiGraph, out_png: str, color_by: str):
    plt.figure(figsize=(8, 6))
    pos  = nx.spring_layout(G, seed=42)
    vals = [edata.get(color_by, 0) for _, _, edata in G.edges(data=True)]

    # разделяем по типам узлов
    real = [n for n, d in G.nodes(data=True) if d.get("is_real_seed")]
    frags = [n for n in G.nodes if n not in real and not n.startswith(("ph_", "rand_", "__", "echo_"))]
    ph   = [n for n in G.nodes if n.startswith(("ph_", "rand_"))]
    echo = [n for n in G.nodes if n.startswith("echo_")]

    nx.draw_networkx_nodes(G, pos, nodelist=real,  node_size=80, node_color="orange")
    nx.draw_networkx_nodes(G, pos, nodelist=frags, node_size=40, node_color="skyblue")
    nx.draw_networkx_nodes(G, pos, nodelist=ph,    node_size=20, node_color="lightcoral")
    nx.draw_networkx_nodes(G, pos, nodelist=echo,  node_size=10, node_color="lightgreen")

    nx.draw_networkx_edges(G, pos, edge_color=vals, edge_cmap=plt.cm.viridis, arrowsize=6)
    plt.axis("off")

    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=150)
    plt.close()


def export_graphml(G: nx.DiGraph, out_graphml: str):
    # очищаем атрибуты
    for k, v in list(G.graph.items()):
        if v is None:
            G.graph.pop(k, None)
        elif isinstance(v, list):
            G.graph[k] = ",".join(map(str, v))

    def clean_attrs(d):
        for a, val in list(d.items()):
            if val is None or isinstance(val, list):
                d.pop(a, None)

    for _, _, data in G.edges(data=True):
        clean_attrs(data)
    for _, data in G.nodes(data=True):
        clean_attrs(data)

    Path(out_graphml).parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(G, out_graphml)
