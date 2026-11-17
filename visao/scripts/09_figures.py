"""Gera as figuras do relatório e do notebook em results/figuras/.

* dataset_distribuicao.png — instâncias por classe em cada divisão (treino/validação/teste)
* dataset_amostras.jpg     — amostras do dataset final com o gabarito desenhado
* sao_paulo_quadros.jpg    — quadros do teste brasileiro (São Paulo) com as predições do modelo final
* treino_curvas.png        — perdas e mAP por época (YOLO26n)

Uso:  python scripts/09_figures.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, DATASET, ROOT, class_names, desenhar_caixas  # noqa: E402

# padrão acadêmico: fonte serifada e títulos fora do gráfico (vão na legenda da figura)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"], "font.size": 10})

OUT = ROOT / "results" / "figuras"
COLORS_BGR = {0: (40, 40, 230), 1: (0, 170, 255), 2: (200, 60, 200)}
COLORS_HEX = ["#d03030", "#e08a00", "#9a3fc0"]
LABEL = {"buraco": "Buraco", "obstaculo": "Obstáculo", "piso_quebrado": "Piso quebrado"}
WEIGHTS = ROOT / "models" / "calcada_yolo26n.pt"


def distribution() -> None:
    stats = json.loads((ROOT / "results" / "dataset_stats.json").read_text(encoding="utf-8"))
    names = class_names()
    splits = [("train", "Treino"), ("val", "Validação"), ("test", "Teste")]
    x = np.arange(len(splits))
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=160)
    width = 0.26
    for k, n in enumerate(names):
        vals = [stats["splits"][s]["instances"].get(n, 0) for s, _ in splits]
        bars = ax.bar(x + (k - 1) * width, vals, width, label=LABEL[n], color=COLORS_HEX[k])
        ax.bar_label(bars, labels=[f"{v:,}".replace(",", ".") for v in vals], fontsize=8, padding=2)
    imgs = [stats["splits"][s]["images"] for s, _ in splits]
    ax.set_xticks(x, [f"{lab}\n({n:,} imagens)".replace(",", ".") for (_, lab), n in zip(splits, imgs)])
    ax.set_ylabel("Instâncias anotadas (caixas)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "dataset_distribuicao.png")
    plt.close(fig)


def draw_boxes(img, boxes, names, with_conf=False):
    itens = [(b[0], b[1], b[2]) if with_conf else (b[0], b[1]) for b in boxes]
    return desenhar_caixas(img, itens, names)


def tile(img, size=(400, 300)):
    h, w = img.shape[:2]
    s = min(size[0] / w, size[1] / h)
    r = cv2.resize(img, (int(w * s), int(h * s)))
    canvas = np.full((size[1], size[0], 3), 30, np.uint8)
    y, x = (size[1] - r.shape[0]) // 2, (size[0] - r.shape[1]) // 2
    canvas[y:y + r.shape[0], x:x + r.shape[1]] = r
    return canvas


def samples() -> None:
    names = class_names()
    rng = random.Random(3)
    labels = sorted((DATASET / "train" / "labels").glob("*.txt"))
    tiles = []
    for c in range(len(names)):
        pool = [l for l in labels if any(int(x.split()[0]) == c for x in l.read_text().splitlines() if x.strip())]
        for lab in rng.sample(pool, 4):
            img_path = next((DATASET / "train" / "images").glob(lab.stem + ".*"))
            img = cv2.imread(str(img_path))
            h, w = img.shape[:2]
            boxes = []
            for line in lab.read_text().splitlines():
                k, xc, yc, bw, bh = line.split()
                xc, yc, bw, bh = map(float, (xc, yc, bw, bh))
                boxes.append((int(k), ((xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h)))
            tiles.append(tile(draw_boxes(img, boxes, names)))
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    cv2.imwrite(str(OUT / "dataset_amostras.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])


def sao_paulo() -> None:
    """Quadros do TESTE brasileiro (trecho final de cada vídeo, nunca usado no treino) com as predições."""
    import json

    from ultralytics import YOLO

    model = YOLO(str(WEIGHTS))
    names = class_names()
    ann = json.loads((ROOT / "configs" / "anotacoes_sp.json").read_text(encoding="utf-8"))
    test_dir = DATA / "sp_frames" / "teste" / "images"
    # um quadro com barreira de cada vídeo, na ordem, mais um quadro sem barreira (controle de falso positivo)
    picks, seen = [], set()
    for img in sorted(test_dir.glob("*.jpg")):
        vid = img.name[:4]
        if ann.get(img.name) and vid not in seen:
            picks.append(img)
            seen.add(vid)
    negatives = [img for img in sorted(test_dir.glob("*.jpg")) if img.name in ann and not ann[img.name]]
    picks = picks[:8] + negatives[:1]
    tiles = []
    for img_path in picks:
        frame = cv2.imread(str(img_path))
        r = model.predict(frame, conf=0.35, verbose=False)[0]
        boxes = [(int(c), b, float(s)) for c, b, s in zip(r.boxes.cls, r.boxes.xyxy.tolist(), r.boxes.conf)]
        tiles.append(tile(draw_boxes(frame, boxes, names, with_conf=True), (533, 300)))
    while len(tiles) % 3:
        tiles.append(np.full_like(tiles[0], 30))
    rows = [np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]
    ok, buf = cv2.imencode(".jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
    (OUT / "sao_paulo_quadros.jpg").write_bytes(buf.tobytes())


def curves() -> None:
    df = pd.read_csv(ROOT / "results" / "treino" / "yolo26n_calcada" / "results.csv")
    df.columns = [c.strip() for c in df.columns]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8), dpi=160)
    tons = [dict(color="black", ls="-"), dict(color="black", ls="--"), dict(color="0.55", ls="-"), dict(color="0.55", ls="--")]
    estilo0, estilo1 = iter(tons), iter(tons)
    for c, lab in (("train/box_loss", "treino (caixa)"), ("val/box_loss", "validação (caixa)"),
                   ("train/cls_loss", "treino (classe)"), ("val/cls_loss", "validação (classe)")):
        if c in df:
            ax[0].plot(df["epoch"], df[c], label=lab, lw=1.3, **next(estilo0))
    ax[0].set_title("(a) Perdas", loc="left", fontsize=10)
    ax[0].set_ylabel("perda")
    ax[0].set_xlabel("época")
    ax[0].legend(frameon=False, fontsize=8)
    for c, lab in (("metrics/mAP50(B)", "mAP50"), ("metrics/mAP50-95(B)", "mAP50-95"),
                   ("metrics/precision(B)", "precisão"), ("metrics/recall(B)", "revocação")):
        ax[1].plot(df["epoch"], df[c], label=lab, lw=1.3, **next(estilo1))
    ax[1].set_title("(b) Métricas na validação", loc="left", fontsize=10)
    ax[1].set_ylabel("valor")
    ax[1].set_xlabel("época")
    ax[1].set_ylim(0, 1)
    ax[1].legend(frameon=False, fontsize=8)
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
        a.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "treino_curvas.png")
    plt.close(fig)


def matriz_e_curva_pr() -> None:
    """Matriz de confusão e curva precisão-revocação do teste, em português e em tons de cinza (relatório)."""
    from ultralytics import YOLO

    names = class_names()
    rot = [LABEL[n] for n in names]
    m = YOLO(str(WEIGHTS)).val(data=str(DATASET / "data.yaml"), split="test", imgsz=640, batch=16,
                               plots=True, verbose=False, project=str(ROOT / "runs"), name="figuras_val", exist_ok=True)
    cmx = m.confusion_matrix.matrix.astype(float)       # linhas = predito, colunas = real (última = fundo)
    norm = cmx / np.maximum(cmx.sum(0, keepdims=True), 1e-9)
    eixo = rot + ["Fundo"]
    fig, ax = plt.subplots(figsize=(5.6, 4.6), dpi=200)
    ax.imshow(norm, cmap="Greys", vmin=0, vmax=1)
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            if i == j == norm.shape[0] - 1:
                continue
            v = norm[i, j]
            ax.text(j, i, f"{v:.2f}".replace(".", ","), ha="center", va="center", fontsize=10,
                    color="white" if v > 0.55 else "black")
    ax.set_xticks(range(len(eixo)), eixo, rotation=20)
    ax.set_yticks(range(len(eixo)), eixo)
    ax.set_xlabel("classe real")
    ax.set_ylabel("classe prevista")
    fig.tight_layout()
    fig.savefig(OUT / "matriz_confusao.png")
    plt.close(fig)

    px, py = m.box.px, m.box.prec_values  # revocação (eixo x) e precisão por classe
    estilos = ["-", "--", ":"]
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=200)
    for k, n in enumerate(rot):
        ax.plot(px, py[k], estilos[k], color="black", lw=1.4, label=f"{n} (AP50 = {m.box.ap50[k]:.3f})".replace(".", ","))
    ax.set_xlabel("revocação")
    ax.set_ylabel("precisão")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "curva_pr.png")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    distribution()
    samples()
    curves()
    sao_paulo()
    matriz_e_curva_pr()
    print("Figuras salvas em", OUT)
