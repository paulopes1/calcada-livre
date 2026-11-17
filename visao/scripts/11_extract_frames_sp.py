"""Etapa 11 — extrai quadros dos vídeos de São Paulo para a adaptação de domínio (Brasil).

* 2 quadros por segundo de cada vídeo (o vídeo noturno fica de fora: iluminação fora do escopo);
* divisão TEMPORAL por vídeo, para não vazar: os primeiros 65% de cada vídeo vão para adaptação
  (treino), há um intervalo de 10% descartado, e os últimos 25% formam o teste brasileiro;
* quase duplicatas (pHash) são removidas dentro de cada parte;
* gera folhas de contato com grade de coordenadas e as pré-anotações do modelo atual, usadas na
  anotação assistida (a pessoa confere, corrige e completa as caixas).

Uso:  python scripts/11_extract_frames_sp.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA  # noqa: E402

FPS_OUT = 2
TRAIN_FRAC, GAP_FRAC = 0.65, 0.10
EXCLUDE = {"Estacionamento da Prosport bloqueando a calçada.webm"}  # noturno
OUT = DATA / "sp_frames"


def main() -> None:
    manifest = []
    for vi, video in enumerate(sorted((DATA / "videos_sp").glob("*.webm"))):
        if video.name in EXCLUDE:
            continue
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur = n / fps
        hashes = {"adapt": [], "teste": []}
        t = 0.0
        while t < dur:
            frac = t / dur
            part = "adapt" if frac < TRAIN_FRAC else ("teste" if frac >= TRAIN_FRAC + GAP_FRAC else None)
            if part:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = cap.read()
                if not ok:
                    break
                h = imagehash.phash(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                if all(h - o > 8 for o in hashes[part]):
                    hashes[part].append(h)
                    if frame.shape[1] < 960:  # vídeos pequenos: amplia para a anotação ficar legível
                        frame = cv2.resize(frame, None, fx=1280 / frame.shape[1], fy=1280 / frame.shape[1],
                                           interpolation=cv2.INTER_CUBIC)
                    name = f"sp{vi:02d}_t{int(t * 10):04d}.jpg"
                    d = OUT / part / "images"
                    d.mkdir(parents=True, exist_ok=True)
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    (d / name).write_bytes(buf.tobytes())
                    manifest.append({"arquivo": name, "parte": part, "video": video.name, "t": round(t, 1)})
            t += 1 / FPS_OUT
        cap.release()
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    for part in ("adapt", "teste"):
        print(part, sum(m["parte"] == part for m in manifest), "quadros")


if __name__ == "__main__":
    main()
