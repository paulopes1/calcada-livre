"""Etapa 5 — detecção em TEMPO REAL em vídeo, webcam ou câmera do celular, com rastreamento.

* Detecta as 3 barreiras quadro a quadro com o YOLO treinado.
* Rastreia cada barreira com ByteTrack, para contar barreiras ÚNICAS (e não uma por quadro).
* Mostra um painel com FPS, contagem por classe e alerta quando a barreira está no caminho.
* Opcional (--api): cada barreira nova confirmada vira uma ocorrência no MVP (POST /detectar),
  enviada em segundo plano para não travar o vídeo.

Uso:
    python scripts/05_video_demo.py --source caminho/video.mp4 --out demo.mp4
    python scripts/05_video_demo.py --source 0 --show                    # webcam
    python scripts/05_video_demo.py --source http://IP:8080/video --show  # celular (app IP Webcam)
    python scripts/05_video_demo.py --source video.mp4 --api http://127.0.0.1:8000 --lat -23.5614 --lon -46.6559
"""
from __future__ import annotations

import argparse
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.video import Anonymizer  # noqa: E402  (mesmo borrão LGPD usado pelo site)
DEFAULT_WEIGHTS = ROOT / "models" / "calcada_yolo26n.pt"
LABELS = {0: "Buraco", 1: "Obstáculo", 2: "Piso quebrado"}
COLORS = {0: (180, 35, 24), 1: (181, 71, 8), 2: (105, 65, 198)}  # RGB, mesmas cores da interface
CONFIRM_FRAMES = 4   # uma barreira só conta depois de aparecer em 4 quadros (evita "piscadas")


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


class Reporter(threading.Thread):
    """Envia ocorrências ao MVP em segundo plano (fila), com novas tentativas se a API cair."""

    def __init__(self, api: str, lat: float | None, lon: float | None):
        super().__init__(daemon=True)
        self.api, self.lat, self.lon = api.rstrip("/"), lat, lon
        self.q: queue.Queue = queue.Queue()
        self.sent = 0
        self.failed = 0

    def run(self):
        while True:
            jpg, step = self.q.get()
            data = {"origem": "video"}
            if self.lat is not None and self.lon is not None:
                # espalha levemente os pontos ao longo da "rota" para o mapa ficar legível
                data["latitude"] = str(self.lat + step * 0.00012)
                data["longitude"] = str(self.lon + step * 0.00008)
            for attempt in range(3):
                try:
                    r = requests.post(f"{self.api}/detectar", files={"foto": ("frame.jpg", jpg, "image/jpeg")},
                                      data=data, timeout=15)
                    if r.ok:
                        self.sent += 1
                        break
                except requests.RequestException:
                    pass
                time.sleep(2 ** attempt)
            else:
                self.failed += 1
            self.q.task_done()


def draw_overlay(frame_bgr, dets, counts, fps, alert, f_small, f_big):
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    s = max(1.0, W / 1280)
    for c, (x0, y0, x1, y1), conf, tid in dets:
        col = COLORS[c]
        d.rectangle([x0, y0, x1, y1], outline=col, width=int(4 * s))
        txt = f"{LABELS[c]} {conf:.0%}" + (f"  #{tid}" if tid is not None else "")
        tb = d.textbbox((0, 0), txt, font=f_small)
        th, tw = tb[3] - tb[1], tb[2] - tb[0]
        ty = max(0, y0 - th - int(10 * s))
        d.rectangle([x0, ty, x0 + tw + int(12 * s), ty + th + int(10 * s)], fill=col + (235,))
        d.text((x0 + int(6 * s), ty + int(3 * s)), txt, font=f_small, fill=(255, 255, 255))
    # painel superior
    bar = int(64 * s)
    d.rectangle([0, 0, W, bar], fill=(15, 23, 42, 215))
    d.text((int(16 * s), int(14 * s)), "Calçada Livre · Visão Computacional", font=f_big, fill=(255, 255, 255))
    info = "   ".join(f"{LABELS[c]}: {counts.get(c, 0)}" for c in LABELS) + f"   |   {fps:4.1f} FPS"
    tb = d.textbbox((0, 0), info, font=f_small)
    d.text((W - (tb[2] - tb[0]) - int(16 * s), int(20 * s)), info, font=f_small, fill=(226, 232, 240))
    if alert:
        msg = f"ATENÇÃO: {alert} à frente"
        tb = d.textbbox((0, 0), msg, font=f_big)
        bw = tb[2] - tb[0] + int(40 * s)
        d.rectangle([(W - bw) // 2, H - int(80 * s), (W + bw) // 2, H - int(20 * s)], fill=(185, 28, 28, 230))
        d.text(((W - bw) // 2 + int(20 * s), H - int(72 * s)), msg, font=f_big, fill=(255, 255, 255))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="arquivo de vídeo, URL de stream ou índice da webcam (0)")
    ap.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    ap.add_argument("--out", default=None, help="salvar vídeo anotado (mp4)")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--show", action="store_true", help="abrir janela ao vivo (tecla Q para sair)")
    ap.add_argument("--api", default=None, help="URL do MVP para registrar ocorrências (ex.: http://127.0.0.1:8000)")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--max-seconds", type=float, default=None, help="limitar a duração processada")
    ap.add_argument("--no-blur", action="store_true", help="desliga o borrão de rostos/placas (não recomendado)")
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.weights)
    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        sys.exit(f"Não consegui abrir a fonte de vídeo: {args.source}")
    fps_in = cap.get(cv2.CAP_PROP_FPS) or 30
    W0, H0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # vídeos pequenos são ampliados para 1280 px de largura, para o painel ficar legível
    up = 1280 / W0 if W0 < 960 else 1.0
    W, H = int(round(W0 * up)) // 2 * 2, int(round(H0 * up)) // 2 * 2
    f_small, f_big = font(int(22 * max(1, W / 1280))), font(int(28 * max(1, W / 1280)))

    writer, tmp_out = None, None
    if args.out:
        tmp_out = Path(args.out).with_suffix(".raw.mp4")
        writer = cv2.VideoWriter(str(tmp_out), cv2.VideoWriter_fourcc(*"mp4v"), fps_in, (W, H))

    anonymize = None if args.no_blur else Anonymizer()
    reporter = None
    if args.api:
        reporter = Reporter(args.api, args.lat, args.lon)
        reporter.start()

    seen_frames: dict[int, int] = defaultdict(int)
    track_cls: dict[int, int] = {}
    confirmed: set[int] = set()
    counts: dict[int, int] = defaultdict(int)
    times: deque = deque(maxlen=30)
    n = 0
    t_start = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.max_seconds and n / fps_in > args.max_seconds:
            break
        if (frame.shape[1], frame.shape[0]) != (W, H):
            frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_CUBIC)
        if anonymize:
            frame = anonymize(frame)
        t0 = time.perf_counter()
        r = model.track(frame, persist=True, conf=args.conf, imgsz=args.imgsz, tracker="bytetrack.yaml",
                        verbose=False, device=0 if _cuda() else "cpu")[0]
        dets, alert = [], None
        if r.boxes is not None and len(r.boxes):
            ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [None] * len(r.boxes)
            for c, box, conf, tid in zip(r.boxes.cls.int().tolist(), r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), ids):
                dets.append((c, box, conf, tid))
                # "no caminho": centro na metade inferior e no terço central da imagem
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                if W / 3 < cx < 2 * W / 3 and cy > H / 2 and conf >= 0.5:
                    alert = LABELS[c].lower()
                if tid is None:
                    continue
                seen_frames[tid] += 1
                track_cls[tid] = c
                if seen_frames[tid] == CONFIRM_FRAMES and tid not in confirmed:
                    confirmed.add(tid)
                    counts[c] += 1
                    if reporter and conf >= 0.5:
                        ok_jpg, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if ok_jpg:
                            reporter.q.put((jpg.tobytes(), len(confirmed)))
        times.append(time.perf_counter() - t0)
        fps = len(times) / sum(times)
        out = draw_overlay(frame, dets, counts, fps, alert, f_small, f_big)
        if writer:
            writer.write(out)
        if args.show:
            cv2.imshow("Calcada Livre - Visao (Q para sair)", out)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        n += 1

    cap.release()
    if writer:
        writer.release()
        final = Path(args.out)
        if shutil.which("ffmpeg"):  # re-encoda em H.264 para tocar em qualquer navegador/YouTube
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp_out), "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", str(final)], check=True)
            tmp_out.unlink()
        else:
            tmp_out.replace(final)
        print(f"Vídeo salvo em {final}")
    if args.show:
        cv2.destroyAllWindows()
    if reporter:
        reporter.q.join()
        print(f"Ocorrências enviadas ao MVP: {reporter.sent} (falhas: {reporter.failed})")
    elapsed = time.time() - t_start
    print(f"Quadros: {n} | tempo: {elapsed:.1f}s | média de inferência: {len(times) / sum(times) if times else 0:.1f} FPS")
    print("Barreiras únicas:", {LABELS[c]: v for c, v in counts.items()})


def _cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


if __name__ == "__main__":
    main()
