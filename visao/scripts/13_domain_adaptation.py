"""Etapa 13 — adaptação de domínio para calçadas brasileiras (São Paulo).

O teste em vídeos reais da Bela Vista mostrou que o modelo treinado só com datasets estrangeiros
não reconhecia piso quebrado típico do Brasil. Esta etapa:

1. converte as anotações assistidas (data/sp_frames/anotacoes.json, ver scripts 11 e 12) para YOLO;
2. faz um fine-tuning curto a partir do modelo atual, juntando o treino original com os quadros de
   adaptação (início de cada vídeo, oversampling x4); a validação continua sendo a original;
3. avalia ANTES e DEPOIS em dois conjuntos de teste: o teste original (para provar que o modelo não
   "esqueceu") e o teste brasileiro (final de cada vídeo, separado no tempo e nunca usado no treino);
4. salva a comparação em results/adaptacao_br.json e uma figura antes × depois.

Uso:  python scripts/13_domain_adaptation.py [--epochs 40]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, DATASET, ROOT, SEED, class_names, desenhar_caixas, seed_everything  # noqa: E402

SP = DATA / "sp_frames"
ANN = ROOT / "configs" / "anotacoes_sp.json"   # anotações versionadas no repositório
OVERSAMPLE = 4
BASE = ROOT / "models" / "calcada_yolo26n_base.pt"   # modelo antes da adaptação
FINAL = ROOT / "models" / "calcada_yolo26n.pt"       # modelo usado pelo MVP


def to_yolo(part: str, copies: int) -> Path:
    ann = json.loads(ANN.read_text(encoding="utf-8"))
    out = SP / f"{part}_yolo"
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "labels").mkdir(parents=True)
    n = 0
    for img in sorted((SP / part / "images").glob("*.jpg")):
        if img.name not in ann:
            continue  # quadro não anotado: fica de fora
        lines = []
        for c, x0, y0, x1, y1 in ann[img.name]:
            lines.append(f"{c} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}")
        for k in range(copies):
            stem = img.stem if k == 0 else f"{img.stem}__os{k}"
            shutil.copy2(img, out / "images" / f"{stem}.jpg")
            (out / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        n += 1
    print(f"{part}: {n} quadros anotados ({n * copies} arquivos)")
    return out / "images"


def write_yaml(path: Path, train, val, test) -> Path:
    path.write_text(yaml.safe_dump({"train": [str(t) for t in train] if isinstance(train, list) else str(train),
                                    "val": str(val), "test": str(test), "nc": 3, "names": class_names()},
                                   allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def metrics(model, data_yaml: Path, tag: str) -> dict:
    m = model.val(data=str(data_yaml), split="test", imgsz=640, batch=16, device=0, plots=True,
                  project=str(ROOT / "runs" / "eval"), name=tag, exist_ok=True, verbose=False)
    out = {"geral": {"precisao": round(float(m.box.mp), 4), "revocacao": round(float(m.box.mr), 4),
                     "mAP50": round(float(m.box.map50), 4), "mAP50_95": round(float(m.box.map), 4)},
           "por_classe": {}}
    present = set(int(i) for i in m.box.ap_class_index)
    for i, n in enumerate(class_names()):
        if i in present:
            p, r, ap50, ap = m.box.class_result(list(m.box.ap_class_index).index(i))
            out["por_classe"][n] = {"precisao": round(float(p), 4), "revocacao": round(float(r), 4),
                                    "mAP50": round(float(ap50), 4), "mAP50_95": round(float(ap), 4)}
    return out


def before_after_figure(base, adapted, imgs: list[Path], out: Path) -> None:
    names = class_names()
    rows = []
    for p in imgs:
        img = cv2.imread(str(p))
        pair = []
        for title, mdl in (("Antes da adaptação", base), ("Depois da adaptação", adapted)):
            r = mdl.predict(img, conf=0.25, verbose=False)[0]
            escala = 640 / img.shape[1]
            im = cv2.resize(img, (640, int(img.shape[0] * escala)))
            itens = [(c, [v * escala for v in b], s) for c, b, s in
                     zip(r.boxes.cls.int().tolist(), r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
            pair.append(desenhar_caixas(im, itens, names, title))
        h = max(x.shape[0] for x in pair)
        pair = [cv2.copyMakeBorder(x, 0, h - x.shape[0], 0, 0, cv2.BORDER_CONSTANT) for x in pair]
        rows.append(np.hstack([pair[0], np.full((h, 8, 3), 255, np.uint8), pair[1]]))
    w = max(r.shape[1] for r in rows)
    grid = np.vstack([np.vstack([r, np.full((8, w, 3), 255, np.uint8)]) for r in rows])
    ok, buf = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 90])
    out.write_bytes(buf.tobytes())


def figura(base, adapted) -> None:
    figs = ROOT / "results" / "figuras"
    figs.mkdir(parents=True, exist_ok=True)
    ann = json.loads(ANN.read_text(encoding="utf-8"))
    picks = []
    for prefix in ("sp03_t03", "sp04_t013", "sp08_t024", "sp07_t008", "sp02_t026"):
        cand = [p for p in sorted((SP / "teste" / "images").glob(f"{prefix}*.jpg")) if ann.get(p.name)]
        if cand:
            picks.append(cand[0])
    before_after_figure(base, adapted, picks, figs / "adaptacao_antes_depois.jpg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--so-figura", action="store_true", help="refaz só a figura antes x depois (não treina)")
    args = ap.parse_args()
    seed_everything()
    from ultralytics import YOLO

    if args.so_figura:
        figura(YOLO(str(BASE)), YOLO(str(FINAL)))
        return

    if not BASE.exists():
        shutil.copy2(FINAL, BASE)  # preserva o modelo pré-adaptação
    adapt_dir = to_yolo("adapt", OVERSAMPLE)
    test_dir = to_yolo("teste", 1)

    y_train = write_yaml(SP / "data_adaptacao.yaml", [DATASET / "train" / "images", adapt_dir],
                         DATASET / "val" / "images", DATASET / "test" / "images")
    y_test_orig = write_yaml(SP / "data_teste_original.yaml", DATASET / "train" / "images",
                             DATASET / "val" / "images", DATASET / "test" / "images")
    y_test_br = write_yaml(SP / "data_teste_br.yaml", DATASET / "train" / "images",
                           DATASET / "val" / "images", test_dir)

    base = YOLO(str(BASE))
    before = {"teste_original": metrics(base, y_test_orig, "base_original"),
              "teste_brasil": metrics(base, y_test_br, "base_brasil")}

    YOLO(str(BASE)).train(
        data=str(y_train), epochs=args.epochs, patience=args.epochs, imgsz=640, batch=32, workers=8, device=0,
        seed=SEED, deterministic=True, optimizer="AdamW", lr0=0.0005, warmup_epochs=1, cos_lr=True,
        close_mosaic=5, hsv_h=0.015, hsv_s=0.6, hsv_v=0.4, degrees=5.0, translate=0.1, scale=0.5, shear=2.0,
        fliplr=0.5, mosaic=1.0, mixup=0.1, project=str(ROOT / "runs"), name="yolo26n_adaptacao_br",
        exist_ok=True, plots=True)
    run_dir = ROOT / "runs" / "yolo26n_adaptacao_br"
    best = run_dir / "weights" / "best.pt"
    keep = ROOT / "results" / "treino" / "yolo26n_adaptacao_br"
    keep.mkdir(parents=True, exist_ok=True)
    for f in ("results.csv",):
        if (run_dir / f).exists():
            shutil.copy2(run_dir / f, keep / f)
    adapted = YOLO(str(best))
    after = {"teste_original": metrics(adapted, y_test_orig, "adapt_original"),
             "teste_brasil": metrics(adapted, y_test_br, "adapt_brasil")}

    n_adapt = len([p for p in (SP / "adapt_yolo" / "images").glob("*.jpg") if "__os" not in p.stem])
    n_test = len(list((SP / "teste_yolo" / "images").glob("*.jpg")))
    result = {"quadros_adaptacao": n_adapt, "oversampling": OVERSAMPLE, "quadros_teste_brasil": n_test,
              "epocas": args.epochs, "antes": before, "depois": after}
    (ROOT / "results" / "adaptacao_br.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # critério de aceitação: melhora no Brasil sem perder mais de 2 pontos de mAP50 no teste original
    gain = after["teste_brasil"]["geral"]["mAP50"] - before["teste_brasil"]["geral"]["mAP50"]
    drop = before["teste_original"]["geral"]["mAP50"] - after["teste_original"]["geral"]["mAP50"]
    if gain > 0 and drop <= 0.02:
        shutil.copy2(best, FINAL)
        print(f"Modelo adaptado ACEITO (+{gain:.3f} mAP50 no Brasil, -{max(drop, 0):.3f} no original) -> {FINAL}")
    else:
        print(f"Modelo adaptado REJEITADO (ganho {gain:.3f}, perda {drop:.3f}); mantido o modelo base")

    figura(base, adapted)


if __name__ == "__main__":
    main()
