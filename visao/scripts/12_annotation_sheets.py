"""Etapa 12 — apoio à anotação assistida dos quadros de São Paulo.

Gera folhas de contato (2x2 quadros) com uma grade de coordenadas a cada 10% e as pré-anotações do
modelo atual (numeradas). Quem anota confere cada folha e registra as caixas corretas em
data/sp_frames/anotacoes.json no formato {arquivo: [[classe, x0, y0, x1, y1], ...]}, com
coordenadas normalizadas (0 a 1). O script 13 converte esse arquivo para rótulos YOLO.

Uso:  python scripts/12_annotation_sheets.py adapt|teste
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, ROOT  # noqa: E402

COLORS = {0: (40, 40, 230), 1: (0, 170, 255), 2: (200, 60, 200)}
TILE_W = 640


def draw_grid(img):
    h, w = img.shape[:2]
    for k in range(1, 10):
        x, y = int(w * k / 10), int(h * k / 10)
        cv2.line(img, (x, 0), (x, h), (255, 255, 255), 1)
        cv2.line(img, (0, y), (w, y), (255, 255, 255), 1)
        cv2.putText(img, f"{k / 10:.1f}", (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        cv2.putText(img, f"{k / 10:.1f}", (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)


def main() -> None:
    part = sys.argv[1]
    from ultralytics import YOLO

    model = YOLO(str(ROOT / "models" / "calcada_yolo26n.pt"))
    imgs = sorted((DATA / "sp_frames" / part / "images").glob("*.jpg"))
    out = DATA / "sp_frames" / f"folhas_{part}"
    out.mkdir(parents=True, exist_ok=True)
    pre = {}
    tiles = []
    for p in imgs:
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        r = model.predict(img, conf=0.15, verbose=False)[0]
        boxes = [[int(c), *(np.array(b) / [w, h, w, h]).round(3).tolist(), round(float(s), 2)]
                 for c, b, s in zip(r.boxes.cls, r.boxes.xyxy.tolist(), r.boxes.conf)]
        pre[p.name] = boxes
        t = cv2.resize(img, (TILE_W, int(h * TILE_W / w)))
        draw_grid(t)
        th, tw = t.shape[:2]
        for k, (c, x0, y0, x1, y1, s) in enumerate(boxes):
            cv2.rectangle(t, (int(x0 * tw), int(y0 * th)), (int(x1 * tw), int(y1 * th)), COLORS[c], 2)
            cv2.putText(t, f"{k}:{'BOP'[c]}{s:.2f}", (int(x0 * tw) + 3, int(y0 * th) + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[c], 2)
        cv2.rectangle(t, (0, th - 24), (tw, th), (0, 0, 0), -1)
        cv2.putText(t, p.name, (6, th - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        tiles.append(t)
    for i in range(0, len(tiles), 4):
        group = tiles[i:i + 4]
        hmax = max(t.shape[0] for t in group)
        group = [cv2.copyMakeBorder(t, 0, hmax - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in group]
        while len(group) < 4:
            group.append(np.zeros_like(group[0]))
        sheet = np.vstack([np.hstack(group[:2]), np.hstack(group[2:])])
        ok, buf = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
        (out / f"folha_{i // 4:03d}.jpg").write_bytes(buf.tobytes())
    (DATA / "sp_frames" / f"pre_anotacoes_{part}.json").write_text(json.dumps(pre, indent=1), encoding="utf-8")
    print(f"{len(imgs)} quadros, {len(range(0, len(tiles), 4))} folhas em {out}")


if __name__ == "__main__":
    main()
