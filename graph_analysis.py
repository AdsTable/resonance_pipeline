#!/usr/bin/env python3
"""
Graph statistics: saves graph_stats.json + degree_histogram.png.
"""

import json
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt

def analyze_graph(G: nx.DiGraph, out_dir: Path):
    stats = {
        "num_nodes": G.number_of_nodes(),
        "num_edges": G.number_of_edges()
    }

    etc = {}
    for *_,d in G.edges(data=True):
        t = d.get("edge_type","plain")
        etc[t] = etc.get(t,0) + 1
    stats["edge_type_counts"] = etc

    comps = list(nx.weakly_connected_components(G))
    stats["num_components"]          = len(comps)
    stats["largest_component_size"]  = max((len(c) for c in comps), default=0)

    dc = nx.degree_centrality(G)
    bc = nx.betweenness_centrality(G)
    stats["top5_by_degree"]      = sorted(dc.items(), key=lambda x:-x[1])[:5]
    stats["top5_by_betweenness"] = sorted(bc.items(), key=lambda x:-x[1])[:5]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "graph_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )

    degs = [d for _,d in G.degree()]
    plt.figure(figsize=(6,4))
    plt.hist(degs, bins=20, color="steelblue", edgecolor="black")
    plt.title("Degree distribution")
    plt.xlabel("Degree")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(out_dir / "degree_histogram.png", dpi=150)
    plt.close()

    return stats
