"""Etapa 7 — separa algumas imagens do conjunto de TESTE em samples/ (versionadas no Git).

Servem para os testes automatizados da API e para qualquer pessoa experimentar o /detectar sem baixar
o dataset inteiro. Escolhe imagens com uma única classe e caixa de tamanho razoável, priorizando
as que o modelo acerta com confiança (exemplos claros para demonstração).

Uso:  python scripts/07_make_samples.py [--per-class 3]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
from common import DATASET, ROOT, class_names  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=3)
    ap.add_argument("--weights", default=str(ROOT / "models" / "calcada_yolo26n.pt"))
    args = ap.parse_args()
    from ultralytics import YOLO

    model = YOLO(args.weights)
    names = class_names()
    out = ROOT / "samples"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    for c, name in enumerate(names):
        picked = 0
        for lab in sorted((DATASET / "test" / "labels").glob("*.txt")):
            lines = [l.split() for l in lab.read_text().splitlines() if l.strip()]
            if not lines or {int(l[0]) for l in lines} != {c}:
                continue
            if max(float(l[3]) * float(l[4]) for l in lines) < 0.04:  # caixa muito pequena
                continue
            img = next((DATASET / "test" / "images").glob(lab.stem + ".*"))
            r = model.predict(str(img), conf=0.5, verbose=False)[0]
            if len(r.boxes) == 0 or int(r.boxes.cls[r.boxes.conf.argmax()]) != c:
                continue
            picked += 1
            cv2.imwrite(str(out / f"{name}_{picked}.jpg"), cv2.imread(str(img)), [cv2.IMWRITE_JPEG_QUALITY, 92])
            if picked == args.per_class:
                break
        print(f"{name}: {picked} amostras")


if __name__ == "__main__":
    main()
