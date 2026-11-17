"""Etapa 1 — baixa os datasets públicos (licença MIT) do Hugging Face, sem precisar de conta.

* Unified Obstacles (Dderedor/obstacles_on_the_road): baixado inteiro (~4 mil imagens).
* ROD-Dataset (Abtinzandi/Obstacle-Detection-Dataset-YOLO): baixamos só as imagens que contêm
  alguma classe mapeada para "obstaculo" + uma amostra de imagens de fundo (sem barreira),
  usando o manifesto oficial do dataset. Isso evita baixar ~24 mil imagens que não usaríamos.

Uso:  python scripts/01_download_datasets.py
"""
from __future__ import annotations

import csv
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from huggingface_hub import HfApi

sys.path.insert(0, str(Path(__file__).parent))
from common import RAW, SEED, load_config  # noqa: E402

HF = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"
UNIFIED = "Dderedor/obstacles_on_the_road"
ROD = "Abtinzandi/Obstacle-Detection-Dataset-YOLO"
BACKGROUND_FRACTION = 0.08  # ~8% de imagens sem barreira ajudam a reduzir falsos positivos

session = requests.Session()
session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))


def wait_from_ratelimit(r: requests.Response) -> int:
    """O Hugging Face limita downloads anônimos (3000 arquivos / 5 min) e informa no cabeçalho
    RateLimit quantos segundos faltam para a janela reabrir (t=...)."""
    header = r.headers.get("RateLimit", "")
    for part in header.split(";"):
        if part.strip().startswith("t="):
            try:
                return int(part.strip()[2:]) + 1
            except ValueError:
                pass
    return 30


def fetch(repo: str, path: str, dest: Path, tries: int = 8) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = HF.format(repo=repo, path=path)
    attempt = 0
    while attempt < tries:
        try:
            r = session.get(url, timeout=60)
            if r.status_code == 200:
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(dest)
                return True
            if r.status_code == 404:
                return False
            if r.status_code == 429:  # limite de taxa: espera a janela reabrir (não conta tentativa)
                time.sleep(wait_from_ratelimit(r))
                continue
            attempt += 1
            time.sleep(min(60, 2 ** attempt))  # 5xx: espera crescente (backoff exponencial)
        except requests.RequestException:
            attempt += 1
            time.sleep(min(60, 2 ** attempt))
    return False


def download_many(repo: str, items: list[tuple[str, Path]], workers: int = 24) -> None:
    ok = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futures = {ex.submit(fetch, repo, p, d): p for p, d in items}
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                ok += 1
            else:
                fail += 1
                print("  falhou:", futures[fut])
            if i % 500 == 0 or i == len(items):
                print(f"  {repo}: {i}/{len(items)} ({time.time() - t0:.0f}s)", flush=True)
    print(f"{repo}: {ok} ok, {fail} falhas")


def download_unified() -> None:
    files = HfApi().list_repo_files(UNIFIED, repo_type="dataset")
    files = [f for f in files if f.startswith("unified_obstacles/")]
    dest = RAW / "unified_obstacles"
    download_many(UNIFIED, [(f, dest / f.removeprefix("unified_obstacles/")) for f in files])


def download_rod() -> None:
    dest = RAW / "rod"
    manifest = dest / "images_manifest.csv"
    for name in ("images_manifest.csv", "data.yaml", "class_distribution.csv"):
        fetch(ROD, name, dest / name)
    wanted = set(load_config()["sources"]["rod"])
    with open(manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    positives, background = [], []
    for row in rows:
        present = {c.strip() for c in row["class_names_present"].split(",") if c.strip()}
        (positives if present & wanted else background).append(row)
    rng = random.Random(SEED)
    background = rng.sample(background, int(len(positives) * BACKGROUND_FRACTION))
    selected = positives + background
    print(f"ROD: {len(positives)} imagens com obstáculo + {len(background)} de fundo")
    # o repositório guarda os arquivos em subpastas numeradas (ex.: train/images/0/IMG_00001.jpg),
    # então montamos o caminho real a partir da listagem oficial do repositório
    remote = {}
    for f in HfApi().list_repo_files(ROD, repo_type="dataset"):
        parts = f.split("/")
        if len(parts) >= 3 and parts[1] in ("images", "labels"):
            remote[(parts[0], parts[1], parts[-1])] = f
    items, missing = [], 0
    for row in selected:
        split = row["split"]
        for kind, fname in (("images", row["image_filename"]), ("labels", row["label_filename"])):
            path = remote.get((split, kind, fname))
            if path is None:
                missing += 1
                continue
            items.append((path, dest / split / kind / fname))
    if missing:
        print(f"ROD: {missing} arquivos do manifesto não existem no repositório (ignorados)")
    download_many(ROD, items)


def download_rupesh() -> None:
    """Reforço da classe buraco: um único .zip (MIT) com ~700 fotos de buracos em formato YOLO."""
    import shutil
    import zipfile

    dest = RAW / "potholes_rupesh"
    if (dest / "data.yaml").exists():
        print("potholes_rupesh: já existe")
        return
    zpath = RAW / "zips" / "pothole_dataset.zip"
    if not fetch("rupesh002/pothole-detection-dataset", "pothole_dataset.zip", zpath):
        print("potholes_rupesh: falha no download")
        return
    tmp = RAW / "_tmp_rupesh"
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(tmp)
    inner = next(tmp.iterdir())
    shutil.move(str(inner), str(dest))
    shutil.rmtree(tmp)
    print("potholes_rupesh: ok")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    download_unified()
    download_rod()
    download_rupesh()
