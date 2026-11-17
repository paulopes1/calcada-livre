"""Análise de vídeo enviada pelo site, exibida AO VIVO no navegador.

Fluxo: o cidadão envia o vídeo (POST /videos) -> o navegador abre /videos/{id}/ao-vivo, que devolve um
fluxo MJPEG: cada quadro é analisado pelo YOLO com rastreamento ByteTrack, desenhado e enviado na hora.
Cada barreira nova confirmada (vista em vários quadros) vira uma ocorrência com origem "video".

LGPD: rostos e placas são borrados antes de qualquer quadro ser exibido ou salvo, e o arquivo de vídeo
original é apagado assim que a análise termina (ou é interrompida).
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .detector import CORES_RGB, LABELS, Deteccao, MODEL_PATH, _fonte

ROOT = Path(__file__).resolve().parents[1]
MAX_VIDEO = 200 * 1024 * 1024        # 200 MB
LARGURA_EXIBICAO = 960               # quadros reduzidos: análise mais rápida e menos banda no navegador
CONF_RASTREIO = 0.35                 # confiança mínima para rastrear
CONF_OCORRENCIA = 0.50               # confiança mínima para virar ocorrência
QUADROS_CONFIRMACAO = 4              # a barreira precisa aparecer em 4 quadros (evita "piscadas")
EXTENSOES = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}


def videos_dir() -> Path:
    p = Path(os.environ.get("VIDEOS_DIR", ROOT / "storage" / "videos"))
    p.mkdir(parents=True, exist_ok=True)
    return p


class Anonymizer:
    """LGPD: borra rostos e placas de veículos antes de exibir/gravar/enviar o quadro.
    Usa os classificadores Haar que já vêm no OpenCV (sem download e rápidos na CPU)."""

    def __init__(self):
        base = cv2.data.haarcascades
        self.cascades = [
            (cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml"), 5, (24, 24)),
            (cv2.CascadeClassifier(base + "haarcascade_profileface.xml"), 5, (24, 24)),
            (cv2.CascadeClassifier(base + "haarcascade_russian_plate_number.xml"), 4, (40, 12)),
        ]
        # desempenho: a busca de rostos/placas roda a cada EVERY quadros, numa cópia reduzida da imagem;
        # nos quadros intermediários o borrão das 2 últimas buscas continua aplicado (nada "vaza")
        self.every = 3
        self.work_width = 480
        self.n = 0
        self.memory: deque = deque(maxlen=2)

    def __call__(self, frame):
        H, W = frame.shape[:2]
        if self.n % self.every == 0:
            k = min(1.0, self.work_width / W)
            small = cv2.resize(frame, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
            found = []
            for casc, neigh, min_size in self.cascades:
                for x, y, w, h in casc.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=neigh, minSize=min_size):
                    found.append(tuple(int(v / k) for v in (x, y, w, h)))
            self.memory.append(found)
        self.n += 1
        for boxes in self.memory:
            for x, y, w, h in boxes:
                x0, y0 = max(0, x - w // 6), max(0, y - h // 6)
                x1, y1 = min(W, x + w + w // 6), min(H, y + h + h // 6)
                roi = frame[y0:y1, x0:x1]
                if roi.size:
                    frame[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (0, 0), sigmaX=max(8, (x1 - x0) / 5))
        return frame


@dataclass
class Analise:
    id: str
    caminho: Path
    latitude: float | None = None
    longitude: float | None = None
    endereco: str | None = None
    status: str = "aguardando"          # aguardando | processando | concluida | interrompida | erro
    quadros: int = 0
    total_quadros: int = 0
    duracao_s: float = 0.0
    fps_medio: float = 0.0
    contagem: dict = field(default_factory=lambda: {"buraco": 0, "obstaculo": 0, "piso_quebrado": 0})
    ocorrencias: list = field(default_factory=list)
    erro: str | None = None
    ultimo_quadro: bytes | None = None

    def resumo(self) -> dict:
        return {"id": self.id, "status": self.status, "quadros": self.quadros, "total_quadros": self.total_quadros,
                "progresso": round(self.quadros / self.total_quadros, 3) if self.total_quadros else None,
                "duracao_s": round(self.duracao_s, 1), "fps_medio": round(self.fps_medio, 1),
                "contagem": self.contagem, "ocorrencias": self.ocorrencias, "erro": self.erro}


ANALISES: dict[str, Analise] = {}
_lock = threading.Lock()


def nova_analise(sufixo: str, latitude, longitude, endereco) -> Analise:
    aid = secrets.token_hex(6)
    a = Analise(id=aid, caminho=videos_dir() / f"{aid}{sufixo}", latitude=latitude, longitude=longitude, endereco=endereco)
    with _lock:
        ANALISES[aid] = a
    return a


def _desenhar(frame_bgr, caixas, contagem, fps, quadro, total) -> np.ndarray:
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    esp = max(3, round(W / 240))
    f_rot = _fonte(max(16, round(W / 42)))
    f_hud = _fonte(max(14, round(W / 56)))
    barra = max(36, round(H / 13))  # altura da faixa superior (HUD)
    for classe, conf, (x0, y0, x1, y1), tid in caixas:
        cor = CORES_RGB.get(classe, (21, 82, 54))
        d.rounded_rectangle([x0, y0, x1, y1], radius=esp * 2, outline=cor + (255,), width=esp)
        txt = f"{LABELS[classe]}  {conf:.0%}" + (f"  #{tid}" if tid is not None else "")
        l, t, r, b = d.textbbox((0, 0), txt, font=f_rot)
        pad = max(5, (b - t) // 3)
        ty = y0 - (b - t) - 2 * pad - esp
        if ty < barra + 6:  # rótulo ficaria escondido sob a faixa: desenha por dentro da caixa
            ty = max(y0, barra + 6) + esp
        d.rounded_rectangle([x0, ty, x0 + (r - l) + 2 * pad, ty + (b - t) + 2 * pad], radius=pad, fill=cor + (240,))
        d.text((x0 + pad - l, ty + pad - t), txt, font=f_rot, fill=(255, 255, 255))
    # faixa superior com o estado da análise
    d.rectangle([0, 0, W, barra], fill=(11, 46, 32, 225))
    esquerda = f"Análise ao vivo · {fps:4.1f} FPS"
    direita = (f"Buraco {contagem['buraco']}   Obstáculo {contagem['obstaculo']}   "
               f"Piso quebrado {contagem['piso_quebrado']}")
    _, t, _, b = d.textbbox((0, 0), esquerda, font=f_hud)
    y = (barra - (b - t)) // 2 - t
    d.text((14, y), esquerda, font=f_hud, fill=(255, 255, 255))
    l2, _, r2, _ = d.textbbox((0, 0), direita, font=f_hud)
    d.text((W - (r2 - l2) - 14, y), direita, font=f_hud, fill=(245, 196, 0))
    if total:  # barra de progresso
        d.rectangle([0, barra, int(W * min(1, quadro / total)), barra + 4], fill=(245, 196, 0, 255))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _iou(a, b) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    uniao = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uniao if uniao > 0 else 0.0


def _barreira_proxima(barreiras, classe, caixa, quadro, fps, largura) -> int | None:
    """Índice de uma barreira da mesma classe vista nos últimos ~4 s perto desta caixa (mesmo objeto)."""
    cx, cy = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
    for i in range(len(barreiras) - 1, -1, -1):
        b = barreiras[i]
        if b["classe"] != classe or quadro - b["quadro"] > 4 * fps:
            continue
        bx, by = (b["caixa"][0] + b["caixa"][2]) / 2, (b["caixa"][1] + b["caixa"][3]) / 2
        if _iou(caixa, b["caixa"]) > 0.2 or ((cx - bx) ** 2 + (cy - by) ** 2) ** 0.5 < 0.2 * largura:
            return i
    return None


def _jpg(frame) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else b""


def _parte(jpg: bytes) -> bytes:
    return b"--quadro\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"


class _Leitor(threading.Thread):
    """Lê e reduz os quadros numa thread própria, em paralelo com a análise.

    Em tempo real, entrega sempre o quadro mais recente no relógio do vídeo (quadros que a análise não
    alcança são pulados, como numa câmera ao vivo). Fora do tempo real (testes), entrega todos, em ordem."""

    def __init__(self, cap, fps: float, ritmo_real: bool):
        super().__init__(daemon=True)
        self.cap, self.fps, self.ritmo_real = cap, fps, ritmo_real
        self.cond = threading.Condition()
        self.fila: deque = deque(maxlen=1 if ritmo_real else 8)
        self.fim = False
        self.parar = False
        self.lidos = 0

    def run(self):
        t0 = time.perf_counter()
        try:
            while not self.parar:
                ok, frame = self.cap.read()
                if not ok:
                    break
                h, w = frame.shape[:2]
                k = LARGURA_EXIBICAO / w
                frame = cv2.resize(frame, (LARGURA_EXIBICAO, int(round(h * k))),
                                   interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
                with self.cond:
                    if not self.ritmo_real:
                        while len(self.fila) == self.fila.maxlen and not self.parar:
                            self.cond.wait(0.1)
                    self.fila.append((self.lidos, frame))
                    self.lidos += 1
                    self.cond.notify_all()
                if self.ritmo_real:
                    espera = t0 + self.lidos / self.fps - time.perf_counter()
                    if espera > 0:
                        time.sleep(espera)
        finally:
            with self.cond:
                self.fim = True
                self.cond.notify_all()

    def proximo(self):
        with self.cond:
            while not self.fila and not self.fim:
                self.cond.wait(0.5)
            if not self.fila:
                return None
            item = self.fila.popleft()
            self.cond.notify_all()
            return item


def transmitir(a: Analise, registrar: Callable[..., dict], ritmo_real: bool = True):
    """Gerador do fluxo MJPEG: analisa, desenha e envia cada quadro; cria as ocorrências no caminho."""
    from ultralytics import YOLO

    a.status = "processando"
    cap = cv2.VideoCapture(str(a.caminho))
    leitor = None
    try:
        if not cap.isOpened():
            raise ValueError("não foi possível ler o vídeo (formatos aceitos: MP4, WEBM, MOV, AVI, MKV)")
        fps_src = cap.get(cv2.CAP_PROP_FPS) or 30
        if not 1 <= fps_src <= 120:
            fps_src = 30
        a.total_quadros = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        a.duracao_s = a.total_quadros / fps_src if a.total_quadros else 0
        modelo = YOLO(str(MODEL_PATH))  # instância própria: o rastreador guarda estado por vídeo
        anon = Anonymizer()
        anon.every, anon.work_width = 4, 400   # versão mais leve do borrão para acompanhar o vídeo
        vistos: dict[int, int] = defaultdict(int)
        confirmados: set[int] = set()
        barreiras: list[dict] = []             # barreiras já registradas: classe, última caixa, último quadro
        trilha_para_barreira: dict[int, int] = {}
        tempos: deque = deque(maxlen=30)
        leitor = _Leitor(cap, fps_src, ritmo_real)
        leitor.start()
        while True:
            item = leitor.proximo()
            if item is None:
                break
            indice, frame = item
            frame = anon(frame)  # LGPD antes de qualquer exibição ou gravação
            t_det = time.perf_counter()
            r = modelo.track(frame, persist=True, conf=CONF_RASTREIO, imgsz=640, tracker="bytetrack.yaml", verbose=False)[0]
            tempos.append(time.perf_counter() - t_det)
            caixas = []
            if r.boxes is not None and len(r.boxes):
                ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [None] * len(r.boxes)
                for c, conf, box, tid in zip(r.boxes.cls.int().tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist(), ids):
                    classe = modelo.names[c]
                    caixas.append((classe, conf, box, tid))
                    if tid is None:
                        continue
                    vistos[tid] += 1
                    if tid in trilha_para_barreira:  # trilha já ligada a uma barreira: só atualiza a posição
                        b = barreiras[trilha_para_barreira[tid]]
                        b["caixa"], b["quadro"] = box, indice
                        continue
                    if vistos[tid] >= QUADROS_CONFIRMACAO and tid not in confirmados and conf >= CONF_OCORRENCIA:
                        confirmados.add(tid)
                        # a mesma barreira pode ganhar outro número de trilha quando alguém passa na frente:
                        # se há uma barreira da mesma classe vista há pouco no mesmo lugar, é a mesma
                        igual = _barreira_proxima(barreiras, classe, box, indice, fps_src, LARGURA_EXIBICAO)
                        if igual is not None:
                            trilha_para_barreira[tid] = igual
                            barreiras[igual]["caixa"], barreiras[igual]["quadro"] = box, indice
                            continue
                        barreiras.append({"classe": classe, "caixa": box, "quadro": indice})
                        trilha_para_barreira[tid] = len(barreiras) - 1
                        a.contagem[classe] += 1
                        n = len(confirmados)
                        lat = a.latitude + (n - 1) * 0.00009 if a.latitude is not None else None
                        lon = a.longitude + (n - 1) * 0.00006 if a.longitude is not None else None
                        o = registrar(frame.copy(), [Deteccao(classe, conf, box)], origem="video",
                                      latitude=lat, longitude=lon, endereco=a.endereco)
                        a.ocorrencias.append({k2: o[k2] for k2 in ("id", "protocolo", "tipo", "confianca", "status")})
            a.quadros = indice + 1
            fps = len(tempos) / sum(tempos) if tempos else 0
            saida = _desenhar(frame, caixas, a.contagem, fps, a.quadros, a.total_quadros)
            jpg = _jpg(saida)
            a.ultimo_quadro = jpg
            yield _parte(jpg)
        a.fps_medio = (len(tempos) / sum(tempos)) if tempos else 0
        a.status = "concluida" if a.quadros else "erro"
        if not a.quadros:
            a.erro = "o vídeo não tem quadros legíveis"
    except GeneratorExit:
        a.status = "interrompida"
        raise
    except Exception as e:  # noqa: BLE001 - o erro vai para o resumo exibido na página
        a.status, a.erro = "erro", str(e)
    finally:
        if leitor is not None:
            leitor.parar = True
            leitor.join(timeout=5)
        cap.release()
        try:
            a.caminho.unlink(missing_ok=True)  # LGPD: o vídeo original não é guardado
        except OSError:
            pass
