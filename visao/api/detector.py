"""Detector de barreiras: carrega o YOLO treinado uma vez e transforma uma foto em detecções.

Também aplica a proteção de dados (LGPD) antes de qualquer imagem ser guardada:
* a foto é decodificada e re-codificada a partir dos pixels, o que descarta TODOS os metadados EXIF
  (inclusive a localização GPS gravada pelo celular e o modelo do aparelho);
* rostos detectados são borrados (Haar cascade do OpenCV, sem dependência externa).
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.environ.get("MODEL_PATH", ROOT / "models" / "calcada_yolo26n.pt"))
CONF_MIN = float(os.environ.get("CONF_MIN", "0.35"))      # abaixo disso a detecção é ignorada
CONF_REVIEW = float(os.environ.get("CONF_REVIEW", "0.60"))  # abaixo disso vai para validação humana
MAX_SIDE = 1280  # fotos maiores são reduzidas: economiza disco e banda sem perder detecção

LABELS = {"buraco": "Buraco", "obstaculo": "Obstáculo", "piso_quebrado": "Piso quebrado"}
CORES_RGB = {"buraco": (180, 35, 24), "obstaculo": (181, 71, 8), "piso_quebrado": (105, 65, 198)}  # mesmas cores da interface


@lru_cache(maxsize=8)
def _fonte(tamanho: int):
    """Fonte legível para as etiquetas; usa a primeira disponível no sistema (Windows, Linux ou macOS)."""
    for nome in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/Library/Fonts/Arial Bold.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()
# prioridade sugerida (a triagem automática do RPA pode recalcular com contexto: escola, hospital, chuva)
PRIORIDADE = {"buraco": "alta", "piso_quebrado": "media", "obstaculo": "media"}


@dataclass
class Deteccao:
    classe: str
    confianca: float
    bbox: list[float]  # [x0, y0, x1, y1] em pixels da imagem processada

    def as_dict(self) -> dict:
        return {"classe": self.classe, "rotulo": LABELS.get(self.classe, self.classe),
                "confianca": round(self.confianca, 4), "bbox": [round(v, 1) for v in self.bbox]}


class Detector:
    def __init__(self, weights: Path = MODEL_PATH):
        from ultralytics import YOLO

        if not weights.exists():
            raise FileNotFoundError(f"Pesos do modelo não encontrados em {weights}")
        self.weights = weights
        self.model = YOLO(str(weights))
        self.names = self.model.names
        self._lock = threading.Lock()  # o modelo não é thread-safe; a API serializa as inferências
        self._faces = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.model.predict(np.zeros((320, 320, 3), np.uint8), verbose=False)  # aquecimento

    @staticmethod
    def decode(data: bytes) -> np.ndarray:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Arquivo não é uma imagem válida (use JPG, PNG ou WEBP).")
        h, w = img.shape[:2]
        if min(h, w) < 64:
            raise ValueError("Imagem pequena demais para análise (mínimo 64 px).")
        scale = MAX_SIDE / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    def blur_faces(self, img: np.ndarray) -> int:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self._faces.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(24, 24))
        for x, y, w, h in faces:
            roi = img[y:y + h, x:x + w]
            img[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (0, 0), sigmaX=max(w, h) / 4)
        return len(faces)

    def detect(self, img: np.ndarray) -> list[Deteccao]:
        with self._lock:
            r = self.model.predict(img, conf=CONF_MIN, imgsz=640, verbose=False)[0]
        out = [Deteccao(self.names[int(c)], float(s), [float(v) for v in b])
               for c, s, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy.tolist())]
        return sorted(out, key=lambda d: -d.confianca)

    @staticmethod
    def annotate(img: np.ndarray, dets: list[Deteccao]) -> np.ndarray:
        """Desenha as caixas no mesmo estilo da interface: contorno arredondado e etiqueta com nome e confiança."""
        rgb = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(rgb, "RGBA")
        lado = max(rgb.size)
        esp = max(3, round(lado / 200))
        fonte = _fonte(max(20, round(lado / 28)))
        for det in dets:
            x0, y0, x1, y1 = det.bbox
            cor = CORES_RGB.get(det.classe, (21, 82, 54))
            d.rounded_rectangle([x0, y0, x1, y1], radius=esp * 2, outline=cor + (255,), width=esp)
            txt = f"{LABELS.get(det.classe, det.classe)}  {det.confianca:.0%}"
            l, t, r, b = d.textbbox((0, 0), txt, font=fonte)
            tw, th = r - l, b - t
            pad = max(6, th // 3)
            ty = y0 - th - 2 * pad - esp if y0 - th - 2 * pad - esp > 0 else y0 + esp
            d.rounded_rectangle([x0, ty, x0 + tw + 2 * pad, ty + th + 2 * pad], radius=pad, fill=cor + (240,))
            d.text((x0 + pad - l, ty + pad - t), txt, font=fonte, fill=(255, 255, 255))
        return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)

    @staticmethod
    def resumo(dets: list[Deteccao]) -> dict:
        """Define o tipo da ocorrência (classe mais confiante), prioridade e se precisa de revisão humana."""
        if not dets:
            return {}
        top = dets[0]
        contagem: dict[str, int] = {}
        for d in dets:
            contagem[d.classe] = contagem.get(d.classe, 0) + 1
        prioridade = PRIORIDADE.get(top.classe, "media")
        if top.classe != "buraco" and sum(contagem.values()) >= 3:
            prioridade = "alta"  # várias barreiras juntas bloqueiam a passagem
        return {"tipo": top.classe, "confianca": round(top.confianca, 4), "prioridade": prioridade,
                "status": "aberta" if top.confianca >= CONF_REVIEW else "pendente_validacao",
                "contagem": contagem}
