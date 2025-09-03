# metrics_collector.py

import os, json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import entropy

def shannon_entropy(data: bytes) -> float:
    counts = pd.Series(list(data)).value_counts(normalize=True)
    return entropy(counts, base=2)

def collect_metrics(frag_dir: str, meta_path: str = None) -> pd.DataFrame:
    metas = {}
    if meta_path and os.path.exists(meta_path):
        metas = json.load(open(meta_path, "r", encoding="utf-8"))

    records = []
    for root, _, files in os.walk(frag_dir):
        for fn in files:
            if not fn.endswith(".bin"):
                continue
            p = os.path.join(root, fn)
            data = open(p, "rb").read()
            rec = {
                "path": p,
                "size": len(data),
                "entropy": shannon_entropy(data),
            }
            # в meta могут быть offset, hamming_distance, pulse_index, detection_score
            rec.update(metas.get(fn, {}))
            records.append(rec)

    return pd.DataFrame(records)


def plot_metrics(df, out_dir, x_col, y_col, hue_col=None):
    os.makedirs(out_dir, exist_ok=True)

    plt.figure(figsize=(8,6))
    sns.boxplot(x=x_col, y=y_col, hue=hue_col, data=df)
    plt.title(f"{y_col} vs {x_col}")
    plt.savefig(f"{out_dir}/{y_col}_by_{x_col}.png")
    plt.close()

    plt.figure(figsize=(8,6))
    sns.histplot(df, x=y_col, hue=hue_col, element="step", stat="density")
    plt.title(f"Distribution of {y_col}")
    plt.savefig(f"{out_dir}/{y_col}_distribution.png")
    plt.close()

    if "invert" in df.columns:
        pivot = df.pivot_table(
            index="wave", columns="invert", values="size", aggfunc="count"
        )
        sns.heatmap(pivot, annot=True, fmt="d")
        plt.title("Частота инверсий по волнам")
        plt.savefig(f"{out_dir}/invert_heatmap.png")
        plt.close()
