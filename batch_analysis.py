# batch_analysis.py

import os, json, subprocess
from concurrent.futures import ThreadPoolExecutor

TOOLS = {
    "file":    ["file", "--mime-type"],
    "strings": ["strings", "-n", "8"],
    "binwalk": ["binwalk", "--json"],
    "exiftool":["exiftool", "-j"],
}

def analyze_file(path: str) -> dict:
    res = {"path": path}
    for name, cmd in TOOLS.items():
        try:
            out = subprocess.check_output(cmd + [path], stderr=subprocess.DEVNULL)
            text = out.decode("utf-8", errors="ignore")
            res[name] = json.loads(text) if name in ("binwalk","exiftool") else text
        except Exception as e:
            res[name] = str(e)
    return res

def batch_analyze(frag_dir: str, jobs: int = 4) -> list:
    paths = [
        os.path.join(r,fn)
        for r, _, fs in os.walk(frag_dir)
        for fn in fs if fn.endswith(".bin")
    ]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(analyze_file, paths))

def save_results(results: list, out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
