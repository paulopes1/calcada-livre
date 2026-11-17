"""Etapa 3 — treino customizado (fine-tuning) do detector YOLO nano nas 3 classes do Calçada Livre.

Parte de pesos pré-treinados no COCO (transfer learning) e ajusta a rede inteira ao nosso dataset.
A cabeça de detecção é recriada para 3 classes automaticamente pelo Ultralytics.

Uso:
    python scripts/03_train.py                       # YOLO26n (modelo principal)
    python scripts/03_train.py --model yolo11n.pt    # YOLO11n (comparação)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATASET, ROOT, SEED, seed_everything  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo26n.pt", help="pesos pré-treinados (COCO) de partida")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--patience", type=int, default=25, help="early stopping (épocas sem melhora)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--name", default=None)
    ap.add_argument("--resume", action="store_true", help="retoma um treino interrompido a partir do last.pt")
    args = ap.parse_args()

    seed_everything()
    from ultralytics import YOLO  # import tardio: deixa o --help rápido

    name = args.name or Path(args.model).stem + "_calcada"
    t0 = time.time()
    last = ROOT / "runs" / name / "weights" / "last.pt"
    if args.resume and last.exists():
        YOLO(str(last)).train(resume=True)
    else:
        _train(YOLO(args.model), args, name)
    finish(args, name, t0)


def _train(model, args, name) -> None:
    model.train(
        data=str(DATASET / "data.yaml"),
        epochs=args.epochs,
        patience=args.patience,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=0,
        seed=SEED,
        deterministic=True,
        optimizer="AdamW",
        lr0=0.002,
        cos_lr=True,
        close_mosaic=10,      # desliga o mosaic nas 10 últimas épocas para estabilizar
        # aumentos de dados pensados para fotos de calçada tiradas com celular
        hsv_h=0.015, hsv_s=0.6, hsv_v=0.4,   # variação de luz/sombra
        degrees=5.0, translate=0.1, scale=0.5, shear=2.0,
        fliplr=0.5, flipud=0.0,               # calçada não aparece de cabeça para baixo
        mosaic=1.0, mixup=0.1,
        project=str(ROOT / "runs"),
        name=name,
        exist_ok=True,
        plots=True,
    )


def finish(args, name, t0) -> None:
    run_dir = ROOT / "runs" / name
    # tempo total de treino lido do results.csv (soma correta mesmo quando o treino foi retomado)
    try:
        import csv
        with open(run_dir / "results.csv", newline="") as f:
            rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)]
        # a coluna "time" é cumulativa e recomeça do zero quando o treino é retomado:
        # somamos o último valor de cada trecho
        times = [float(r["time"]) for r in rows]
        total = sum(t for t, nxt in zip(times, times[1:] + [0.0]) if nxt < t)
        minutes = total / 60
        epochs_done = int(float(rows[-1]["epoch"]))
    except Exception:
        minutes, epochs_done = (time.time() - t0) / 60, None
    best = run_dir / "weights" / "best.pt"
    models_dir = ROOT / "models"
    models_dir.mkdir(exist_ok=True)
    shutil.copy2(best, models_dir / f"{name}_best.pt")
    info = {"modelo_base": args.model, "epocas_max": args.epochs, "epocas_executadas": epochs_done,
            "imgsz": args.imgsz, "batch": args.batch, "tempo_treino_min": round(minutes, 1),
            "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/")}
    (run_dir / "train_info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    # cópia leve (versionada) das curvas e do resumo do treino, já que runs/ não vai para o Git
    keep = ROOT / "results" / "treino" / name
    keep.mkdir(parents=True, exist_ok=True)
    for f in ("results.csv", "train_info.json"):  # args.yaml fica de fora (tem caminhos locais)
        if (run_dir / f).exists():
            shutil.copy2(run_dir / f, keep / f)
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
