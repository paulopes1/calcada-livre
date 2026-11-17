"""Utilidades compartilhadas pelos scripts do pipeline de visão do Calçada Livre."""
from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "classes.yaml"

# Pasta de dados fora do repositório (os datasets ocupam alguns GB).
# Pode ser trocada com a variável de ambiente CALCADA_DATA.
DATA = Path(os.environ.get("CALCADA_DATA", ROOT / "data")).resolve()
RAW = DATA / "raw"
DATASET = DATA / "calcada_livre"  # dataset final, no formato YOLO

SEED = 42


def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def load_config() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def class_names() -> list[str]:
    cfg = load_config()
    return [cfg["classes"][i] for i in sorted(cfg["classes"])]


# ------------------------------------------------------------------ figuras com acentuação
ROTULOS = {"buraco": "Buraco", "obstaculo": "Obstáculo", "piso_quebrado": "Piso quebrado"}
CORES_RGB = {"buraco": (200, 40, 40), "obstaculo": (230, 120, 0), "piso_quebrado": (150, 60, 190)}


def _fonte(tamanho: int):
    from PIL import ImageFont
    for nome in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        for pasta in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"):
            caminho = Path(pasta) / nome
            if caminho.exists():
                return ImageFont.truetype(str(caminho), tamanho)
    return ImageFont.load_default()


def desenhar_caixas(img_bgr, itens, nomes: list[str], titulo: str | None = None):
    """Desenha caixas com rótulo acentuado (ex.: "Obstáculo 0,74") e, opcionalmente, uma faixa de título.

    itens: lista de (classe, caixa_xyxy) ou (classe, caixa_xyxy, confiança).
    """
    import cv2
    from PIL import Image, ImageDraw

    im = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(im)
    W = im.width
    esp = max(2, round(W / 220))
    f_rot = _fonte(max(13, round(W / 34)))
    for it in itens:
        nome = nomes[int(it[0])]
        x0, y0, x1, y1 = (int(v) for v in it[1])
        cor = CORES_RGB.get(nome, (40, 40, 40))
        d.rectangle([x0, y0, x1, y1], outline=cor, width=esp)
        txt = ROTULOS.get(nome, nome) + (f" {it[2]:.2f}".replace(".", ",") if len(it) > 2 else "")
        l, t, r, b = d.textbbox((0, 0), txt, font=f_rot)
        pad = max(3, (b - t) // 4)
        ty = y0 - (b - t) - 2 * pad if y0 - (b - t) - 2 * pad >= 0 else y0
        d.rectangle([x0, ty, x0 + (r - l) + 2 * pad, ty + (b - t) + 2 * pad], fill=cor)
        d.text((x0 + pad - l, ty + pad - t), txt, font=f_rot, fill=(255, 255, 255))
    if titulo:
        f_tit = _fonte(max(14, round(W / 28)))
        l, t, r, b = d.textbbox((0, 0), titulo, font=f_tit)
        faixa = (b - t) + 16
        d.rectangle([0, 0, W, faixa], fill=(25, 25, 25))
        d.text((10 - l, 8 - t), titulo, font=f_tit, fill=(255, 255, 255))
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
