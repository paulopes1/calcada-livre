"""Etapa 2 — monta o dataset customizado "Calçada Livre" (3 classes) no formato YOLO.

O que este script faz, na ordem:
1. Lê os rótulos dos dois datasets de origem e remapeia as classes para a taxonomia do projeto
   (configs/classes.yaml): buraco, obstaculo, piso_quebrado. Classes fora do escopo são removidas.
2. Saneia as caixas: converte polígonos em caixas, recorta para [0, 1] e descarta caixas degeneradas.
3. Remove duplicatas exatas e agrupa quase-duplicatas por hash perceptual (pHash). O Unified
   Obstacles usa oversampling (cópias da mesma foto) e exports do Roboflow costumam ter variações
   aumentadas da mesma imagem: se cópias caíssem em treino e teste, as métricas ficariam infladas.
4. Divide em treino/validação/teste (80/10/10) por grupo, com semente fixa, estratificando pela
   classe mais rara presente em cada imagem.
5. Grava o dataset, o data.yaml e as estatísticas usadas no relatório.

Uso:  python scripts/02_build_dataset.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import imagehash
import numpy as np
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from common import DATASET, RAW, ROOT, SEED, class_names, load_config, seed_everything  # noqa: E402

SPLITS = {"train": 0.8, "val": 0.1, "test": 0.1}
NEAR_DUP_HAMMING = 6     # distância máxima entre pHashes para considerar "mesma foto"
MIN_BOX_SIDE = 0.004     # caixas com lado < 0,4% da imagem são ruído de anotação
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
OVERSAMPLE = {"piso_quebrado": 3}  # cópias por imagem de treino que contém a classe (aumentos as tornam diferentes)


def read_source_names(yaml_path: Path) -> list[str]:
    with open(yaml_path, encoding="utf-8") as f:
        return [str(n).strip() for n in yaml.safe_load(f)["names"]]


class CorruptLabel(Exception):
    """Arquivo de rótulo com conteúdo que não é anotação YOLO (descartamos a imagem inteira)."""


def parse_label(path: Path, src_names: list[str], mapping: dict[str, str], target: dict[str, int]):
    """Retorna (caixas_mapeadas, n_caixas_descartadas). Lança CorruptLabel se o arquivo não for YOLO válido."""
    boxes, dropped = [], 0
    if not path.exists():
        return boxes, dropped
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            cid = int(float(parts[0]))
            vals = list(map(float, parts[1:]))
        except ValueError as e:
            raise CorruptLabel(path.name) from e
        if len(vals) < 4 or len(vals) % 2 or not all(-0.01 <= v <= 1.01 for v in vals):
            raise CorruptLabel(path.name)
        if len(vals) == 4:
            xc, yc, w, h = vals
        else:  # polígono (segmentação) -> caixa envolvente
            xs, ys = vals[0::2], vals[1::2]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            xc, yc, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        name = src_names[cid] if cid < len(src_names) else None
        if name not in mapping:
            dropped += 1
            continue
        # recorta para dentro da imagem
        x0, y0 = max(0.0, xc - w / 2), max(0.0, yc - h / 2)
        x1, y1 = min(1.0, xc + w / 2), min(1.0, yc + h / 2)
        w, h = x1 - x0, y1 - y0
        if w < MIN_BOX_SIDE or h < MIN_BOX_SIDE:
            dropped += 1
            continue
        boxes.append((target[mapping[name]], (x0 + x1) / 2, (y0 + y1) / 2, w, h))
    return boxes, dropped


MAX_BOX_AREA = {"potholes_rupesh": 0.70}   # filtro de qualidade por fonte (caixa absurda = anotação ruim)
KEEP_BACKGROUND = {"rod"}                   # fontes cujas imagens sem caixa mapeada viram "fundo" (negativos)
SKIPPED: Counter = Counter()


def collect() -> list[dict]:
    """Lê todas as fontes declaradas em configs/classes.yaml que existirem em data/raw/."""
    cfg = load_config()
    target = {n: i for i, n in enumerate(class_names())}
    records = []
    for src, mapping in cfg["sources"].items():
        base = RAW / src
        if not (base / "data.yaml").exists():
            print(f"  (fonte {src} não encontrada em {base}, ignorada)")
            continue
        names = read_source_names(base / "data.yaml")
        for split_dir in ("train", "valid", "test"):
            for img in sorted((base / split_dir / "images").glob("*")):
                if img.suffix.lower() not in IMG_EXT:
                    continue
                try:
                    boxes, dropped = parse_label(base / split_dir / "labels" / (img.stem + ".txt"), names, mapping, target)
                except CorruptLabel:
                    SKIPPED["rotulo_corrompido"] += 1
                    continue
                if boxes and src in MAX_BOX_AREA and max(b[3] * b[4] for b in boxes) > MAX_BOX_AREA[src]:
                    SKIPPED["caixa_gigante"] += 1
                    continue
                if not boxes and src not in KEEP_BACKGROUND:
                    SKIPPED["so_classes_descartadas"] += 1  # ex.: só tinha "animal" ou "fence"
                    continue
                records.append({"src": src, "img": img, "boxes": boxes, "dropped": dropped})
    return records


def phash_all(records: list[dict]) -> np.ndarray:
    hashes = []
    for i, r in enumerate(records):
        try:
            with Image.open(r["img"]) as im:
                im.verify()
            with Image.open(r["img"]) as im:
                h = imagehash.phash(im.convert("RGB"))
            hashes.append(int(str(h), 16))
            r["ok"] = True
        except Exception:
            hashes.append(0)
            r["ok"] = False
        if (i + 1) % 2000 == 0:
            print(f"  pHash {i + 1}/{len(records)}", flush=True)
    return np.array(hashes, dtype=np.uint64)


def popcount64(x: np.ndarray) -> np.ndarray:
    # contagem de bits vetorizada (SWAR)
    x = x - ((x >> np.uint64(1)) & np.uint64(0x5555555555555555))
    x = (x & np.uint64(0x3333333333333333)) + ((x >> np.uint64(2)) & np.uint64(0x3333333333333333))
    x = (x + (x >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
    return ((x * np.uint64(0x0101010101010101)) >> np.uint64(56)).astype(np.int32)


def group_duplicates(hashes: np.ndarray):
    """Union-find sobre pares com distância de Hamming <= limiar. Retorna (grupo, é_duplicata_exata)."""
    n = len(hashes)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    exact = np.zeros(n, dtype=bool)
    for i in range(n - 1):
        d = popcount64(np.bitwise_xor(hashes[i + 1:], hashes[i]))
        for off in np.nonzero(d <= NEAR_DUP_HAMMING)[0]:
            j = i + 1 + int(off)
            if d[off] == 0:
                exact[j] = True
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri
    return np.array([find(i) for i in range(n)]), exact


def split_groups(records: list[dict], groups: np.ndarray) -> dict[int, str]:
    rng = np.random.default_rng(SEED)
    by_group = defaultdict(list)
    for idx, g in enumerate(groups):
        by_group[g].append(idx)
    # frequência global de cada classe para achar a "mais rara" de cada grupo
    freq = Counter(b[0] for r in records for b in r["boxes"])
    strata = defaultdict(list)
    for g, idxs in by_group.items():
        cls = {b[0] for i in idxs for b in records[i]["boxes"]}
        key = min(cls, key=lambda c: freq[c]) if cls else -1  # -1 = fundo
        strata[key].append(g)
    assign = {}
    for key, gs in strata.items():
        gs = list(gs)
        rng.shuffle(gs)
        n = len(gs)
        n_tr, n_va = int(round(n * SPLITS["train"])), int(round(n * SPLITS["val"]))
        for k, g in enumerate(gs):
            assign[g] = "train" if k < n_tr else ("val" if k < n_tr + n_va else "test")
    return assign


def main() -> None:
    seed_everything()
    names = class_names()
    print("Lendo rótulos de origem...")
    records = collect()
    print(f"  {len(records)} imagens candidatas")
    print("Calculando pHash para deduplicação...")
    hashes = phash_all(records)
    groups, exact = group_duplicates(hashes)

    keep = [i for i, r in enumerate(records) if r["ok"] and not exact[i]]
    n_corrupt = sum(not r["ok"] for r in records)
    n_exact = int(exact.sum())
    records = [records[i] for i in keep]
    groups = groups[keep]
    assign = split_groups(records, groups)

    if DATASET.exists():
        shutil.rmtree(DATASET)
    stats = {s: {"images": 0, "background": 0, "instances": Counter(), "by_source": Counter(), "oversampled_copies": 0}
             for s in SPLITS}
    for r, g in zip(records, groups):
        split = assign[g]
        stem = f"{r['src']}__{r['img'].stem}"
        (DATASET / split / "images").mkdir(parents=True, exist_ok=True)
        (DATASET / split / "labels").mkdir(parents=True, exist_ok=True)
        # oversampling SÓ no treino para a classe rara (validação/teste ficam intactos, sem vazamento)
        copies = 1
        if split == "train":
            copies = max([OVERSAMPLE.get(names[b[0]], 1) for b in r["boxes"]] or [1])
        for k in range(copies):
            s = stem if k == 0 else f"{stem}__os{k}"
            shutil.copy2(r["img"], DATASET / split / "images" / (s + r["img"].suffix.lower()))
            with open(DATASET / split / "labels" / (s + ".txt"), "w", encoding="utf-8") as f:
                for c, xc, yc, w, h in r["boxes"]:
                    f.write(f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
        st = stats[split]
        st["images"] += 1
        st["oversampled_copies"] += copies - 1
        st["background"] += int(not r["boxes"])
        st["by_source"][r["src"]] += 1
        for b in r["boxes"]:
            st["instances"][names[b[0]]] += 1

    data_yaml = {"path": str(DATASET), "train": "train/images", "val": "val/images", "test": "test/images",
                 "nc": len(names), "names": names}
    with open(DATASET / "data.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data_yaml, f, allow_unicode=True, sort_keys=False)

    summary = {
        "candidatas": len(keep) + n_corrupt + n_exact,
        "corrompidas_removidas": n_corrupt,
        "duplicatas_exatas_removidas": n_exact,
        "grupos_de_quase_duplicatas": int(len(set(groups.tolist()))),
        "descartadas_na_leitura": dict(SKIPPED),
        "final": len(records),
        "oversampling_treino": OVERSAMPLE,
        "splits": {s: {"images": v["images"], "background": v["background"],
                       "oversampled_copies": v["oversampled_copies"],
                       "instances": dict(v["instances"]), "by_source": dict(v["by_source"])}
                   for s, v in stats.items()},
    }
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "dataset_stats.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
