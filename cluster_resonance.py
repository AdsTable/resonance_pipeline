# cluster_resonance.py

import os, json
import pandas as pd
from sklearn.preprocessing import StandardScaler
import umap, hdbscan

def load_batch_results(json_path: str) -> pd.DataFrame:
    data = json.load(open(json_path, "r", encoding="utf-8"))
    recs = []
    for r in data:
        recs.append({
            "path": r["path"],
            "size": os.path.getsize(r["path"]),
            "strings": len(r.get("strings","").splitlines()),
        })
    return pd.DataFrame(recs)

def extract_features(df: pd.DataFrame):
    X = df[["size","strings"]].values
    return StandardScaler().fit_transform(X)

def cluster_and_select(df: pd.DataFrame, n_neighbors: int = 15):
    X = extract_features(df)
    emb = umap.UMAP(n_neighbors=n_neighbors, min_dist=0.1).fit_transform(X)
    labels = hdbscan.HDBSCAN(min_cluster_size=5).fit_predict(emb)

    df["cluster_label"] = labels
    df["umap_x"], df["umap_y"] = emb[:,0], emb[:,1]

    seeds = []
    for c in set(labels):
        if c < 0: continue
        members = df[df["cluster_label"]==c]
        idx = len(members)//2
        seeds.append(members.iloc[idx]["path"])
    return df, seeds
