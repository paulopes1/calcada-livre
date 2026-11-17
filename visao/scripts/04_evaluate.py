"""Etapa 4 — avaliação no conjunto de TESTE (imagens que o modelo nunca viu no treino nem na validação).

Gera, para cada modelo informado:
* métricas gerais e por classe: precisão, revocação, mAP50 e mAP50-95 (results/<modelo>/metrics.json);
* matriz de confusão, curvas PR e F1 (PNG gerados pelo Ultralytics);
* velocidade: FPS medido ponta a ponta com batch=1 na GPU e na CPU (requisito de tempo real);
* exemplos de ACERTO e de ERRO lado a lado com o gabarito (results/<modelo>/exemplos/).

Uso:
    python scripts/04_evaluate.py models/yolo26n_calcada_best.pt [models/yolo11n_calcada_best.pt ...]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from common import DATASET, ROOT, class_names, desenhar_caixas, seed_everything  # noqa: E402

COLORS = {0: (40, 40, 230), 1: (0, 170, 255), 2: (200, 60, 200)}  # BGR: buraco, obstaculo, piso_quebrado
IOU_MATCH = 0.5
CONF = 0.25


def load_gt(label: Path, w: int, h: int):
    out = []
    if label.exists():
        for line in label.read_text().splitlines():
            p = line.split()
            if len(p) == 5:
                c, xc, yc, bw, bh = int(p[0]), *map(float, p[1:])
                out.append((c, np.array([(xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h])))
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(gts, preds):
    """Casamento guloso por confiança. Retorna (tp, fp, fn, confusões_de_classe)."""
    used, tp, fp, conf_err = set(), 0, 0, 0
    for c, box, _ in sorted(preds, key=lambda p: -p[2]):
        best, best_j = 0.0, -1
        for j, (gc, gbox) in enumerate(gts):
            if j in used:
                continue
            v = iou(box, gbox)
            if v > best:
                best, best_j = v, j
        if best >= IOU_MATCH and gts[best_j][0] == c:
            used.add(best_j)
            tp += 1
        else:
            fp += 1
            if best >= IOU_MATCH:
                conf_err += 1
    return tp, fp, len(gts) - len(used), conf_err


def draw(img, items, names, title):
    return desenhar_caixas(img, items, names, title)


def side_by_side(img, gts, preds, names):
    h, w = img.shape[:2]
    scale = 480 / max(h, w)
    img = cv2.resize(img, (int(w * scale), int(h * scale)))
    gts = [(c, b * scale) for c, b in gts]
    preds = [(c, b * scale, s) for c, b, s in preds]
    left = draw(img, gts, names, "Gabarito (anotação)")
    right = draw(img, preds, names, "Predição do modelo")
    sep = np.full((img.shape[0], 8, 3), 255, np.uint8)
    return np.hstack([left, sep, right])


def save_jpg(path: Path, img) -> None:
    """Salva JPEG via imencode + Python (o cv2.imwrite falha em silêncio com caminhos longos no Windows)."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError(f"falha ao codificar {path.name}")
    path.write_bytes(buf.tobytes())


def benchmark(model, images: list[Path], device: str, n: int = 150) -> float:
    imgs = [cv2.imread(str(p)) for p in images[:n]]
    for im in imgs[:10]:  # aquecimento
        model.predict(im, device=device, verbose=False, conf=CONF)
    if device != "cpu":
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for im in imgs:
        model.predict(im, device=device, verbose=False, conf=CONF)
    if device != "cpu":
        torch.cuda.synchronize()
    return len(imgs) / (time.perf_counter() - t0)


def exemplos(model, test_imgs, names, out: Path) -> list[dict]:
    """Salva exemplos de acerto e de erro lado a lado com o gabarito (results/<modelo>/exemplos/)."""
    ex_dir = out / "exemplos"
    if ex_dir.exists():
        shutil.rmtree(ex_dir)
    ex_dir.mkdir()
    scored = []
    for p in test_imgs:
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        gts = load_gt(DATASET / "test" / "labels" / (p.stem + ".txt"), w, h)
        r = model.predict(img, conf=CONF, device=0, verbose=False)[0]
        preds = [(int(c), b.cpu().numpy(), float(s)) for c, b, s in zip(r.boxes.cls, r.boxes.xyxy, r.boxes.conf)]
        tp, fp, fn, ce = match(gts, preds)
        scored.append({"img": p, "gts": gts, "preds": preds, "tp": tp, "fp": fp, "fn": fn, "ce": ce})

    rng = np.random.default_rng(7)

    def pick(idxs: list[int], n: int) -> list[int]:
        return [int(i) for i in rng.choice(idxs, size=min(n, len(idxs)), replace=False)] if idxs else []

    # acertos: tudo certo e pelo menos 1 TP; até 2 por classe para variar (trabalha com índices)
    hits = [i for i, s in enumerate(scored) if s["tp"] >= 1 and s["fp"] == 0 and s["fn"] == 0]
    chosen_hits: list[int] = []
    for c in range(len(names)):
        pool = [i for i in hits if any(g[0] == c for g in scored[i]["gts"]) and i not in chosen_hits]
        chosen_hits += pick(pool, 2)
    # erros: falso negativo, falso positivo e confusão de classe
    # nomes curtos de arquivo: fn = falso negativo, fp = falso positivo, classe = confusão de classe
    errors = {
        # falso negativo "puro": o modelo não marcou nada na imagem (caso mais didático);
        # se não houver nenhum, usa imagens com alguma barreira perdida
        "fn": ([i for i, s in enumerate(scored) if s["fn"] >= 1 and not s["preds"]]
               or [i for i, s in enumerate(scored) if s["fn"] >= 1 and s["fp"] == 0]),
        "fp": [i for i, s in enumerate(scored) if s["fp"] >= 1 and s["fn"] == 0 and s["ce"] == 0],
        "classe": [i for i, s in enumerate(scored) if s["ce"] >= 1],
    }
    for k, i in enumerate(chosen_hits):
        s = scored[i]
        save_jpg(ex_dir / f"acerto_{k + 1}.jpg", side_by_side(cv2.imread(str(s["img"])), s["gts"], s["preds"], names))
    for kind, pool in errors.items():
        chosen = pick(pool, 2)
        print(f"  exemplos de {kind}: {len(pool)} imagens candidatas, {len(chosen)} salvas")
        for k, i in enumerate(chosen):
            s = scored[i]
            save_jpg(ex_dir / f"erro_{kind}_{k + 1}.jpg",
                     side_by_side(cv2.imread(str(s["img"])), s["gts"], s["preds"], names))

    return scored


def evaluate(weights: Path, so_exemplos: bool = False) -> dict | None:
    from ultralytics import YOLO

    names = class_names()
    tag = weights.stem.replace("_best", "")
    out = ROOT / "results" / tag
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(weights))

    test_imgs = sorted((DATASET / "test" / "images").glob("*"))
    if so_exemplos:  # só refaz as figuras de exemplo, sem tocar nas métricas já salvas
        exemplos(model, test_imgs, names, out)
        return None

    # 1) métricas oficiais no split de teste
    val_dir = ROOT / "runs" / "eval"
    m = model.val(data=str(DATASET / "data.yaml"), split="test", imgsz=640, batch=16, device=0,
                  plots=True, project=str(val_dir), name=tag, exist_ok=True, verbose=False)
    per_class = {}
    for i, n in enumerate(names):
        p, r, ap50, ap = m.box.class_result(i)
        per_class[n] = {"precisao": round(float(p), 4), "revocacao": round(float(r), 4),
                        "mAP50": round(float(ap50), 4), "mAP50_95": round(float(ap), 4)}
    for f in ("confusion_matrix_normalized.png", "confusion_matrix.png", "BoxPR_curve.png", "BoxF1_curve.png",
              "BoxP_curve.png", "BoxR_curve.png"):
        if (val_dir / tag / f).exists():
            shutil.copy2(val_dir / tag / f, out / f)

    # 2) velocidade ponta a ponta (pré-processamento + inferência + pós-processamento), batch=1
    fps_gpu = benchmark(model, test_imgs, "0")
    fps_cpu = benchmark(model, test_imgs, "cpu", n=60)

    # 3) exemplos de acerto e de erro
    scored = exemplos(model, test_imgs, names, out)

    tot = {k: int(sum(s[k] for s in scored)) for k in ("tp", "fp", "fn", "ce")}
    metrics = {
        "modelo": tag,
        "pesos": str(weights.relative_to(ROOT)) if weights.is_relative_to(ROOT) else str(weights),
        "imagens_teste": len(test_imgs),
        "geral": {"precisao": round(float(m.box.mp), 4), "revocacao": round(float(m.box.mr), 4),
                  "mAP50": round(float(m.box.map50), 4), "mAP50_95": round(float(m.box.map), 4)},
        "por_classe": per_class,
        "velocidade": {"fps_gpu_batch1": round(fps_gpu, 1), "fps_cpu_batch1": round(fps_cpu, 1),
                       "gpu": torch.cuda.get_device_name(0), "ms_por_imagem_val": {k: round(v, 2) for k, v in m.speed.items()}},
        "contagem_conf_0.25_iou_0.5": {"verdadeiros_positivos": tot["tp"], "falsos_positivos": tot["fp"],
                                       "falsos_negativos": tot["fn"], "confusoes_de_classe": tot["ce"]},
        "parametros": int(sum(p.numel() for p in model.model.parameters())),
        "tamanho_mb": round(weights.stat().st_size / 1e6, 2),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", nargs="+", type=Path)
    ap.add_argument("--so-exemplos", action="store_true", help="refaz só as figuras de exemplo (não mexe nas métricas)")
    args = ap.parse_args()
    seed_everything()
    if args.so_exemplos:
        for w in args.weights:
            evaluate(w.resolve(), so_exemplos=True)
        return
    all_m = [evaluate(w.resolve()) for w in args.weights]
    lines = ["| Modelo | Precisão | Revocação | mAP50 | mAP50-95 | FPS GPU | FPS CPU | Tamanho |",
             "|---|---|---|---|---|---|---|---|"]
    for m in all_m:
        g, v = m["geral"], m["velocidade"]
        lines.append(f"| {m['modelo']} | {g['precisao']:.3f} | {g['revocacao']:.3f} | {g['mAP50']:.3f} | "
                     f"{g['mAP50_95']:.3f} | {v['fps_gpu_batch1']} | {v['fps_cpu_batch1']} | {m['tamanho_mb']} MB |")
    (ROOT / "results" / "comparacao.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
