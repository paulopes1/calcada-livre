"""API de Visão do MVP Calçada Livre.

O cidadão envia a foto da calçada para POST /detectar; o YOLO identifica a barreira e a ocorrência
"nasce" com tipo, confiança, prioridade sugerida e status já preenchidos. Detecções com confiança
baixa entram como "pendente_validacao" para uma pessoa da zeladoria confirmar (humano no circuito).

Rodar:  uvicorn api.main:app --host 0.0.0.0 --port 8000
Docs interativas (Swagger): http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, integracao_mvp
from . import video as video_mod
from .detector import CONF_MIN, CONF_REVIEW, LABELS, Detector

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB

log = logging.getLogger("calcada.visao")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
state: dict = {}


def photos_dir() -> Path:
    p = Path(os.environ.get("PHOTOS_DIR", ROOT / "storage" / "fotos"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    state["detector"] = Detector()
    log.info("Modelo carregado: %s", state["detector"].weights.name)
    yield


app = FastAPI(
    title="Calçada Livre · API de Visão Computacional",
    description="Detecta buracos, obstáculos e piso quebrado em fotos de calçadas e registra ocorrências.",
    version="1.0.0",
    lifespan=lifespan,
)


class Status(str, Enum):
    pendente_validacao = "pendente_validacao"
    aberta = "aberta"
    validada = "validada"
    rejeitada = "rejeitada"
    resolvida = "resolvida"


class Tipo(str, Enum):
    buraco = "buraco"
    obstaculo = "obstaculo"
    piso_quebrado = "piso_quebrado"


class Atualizacao(BaseModel):
    status: Status | None = None
    tipo: Tipo | None = Field(None, description="Correção humana do tipo detectado")
    prioridade: str | None = Field(None, pattern="^(baixa|media|alta)$")
    descricao: str | None = Field(None, max_length=500)
    endereco: str | None = Field(None, max_length=200, description="Correção do endereço")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


@app.get("/saude", tags=["infra"])
def saude():
    det: Detector = state["detector"]
    return {"status": "ok", "modelo": det.weights.name, "classes": list(det.names.values()),
            "limiar_deteccao": CONF_MIN, "limiar_validacao_humana": CONF_REVIEW}


@app.post("/detectar", tags=["visão"], status_code=201)
async def detectar(
    foto: UploadFile = File(..., description="Foto da calçada (JPG, PNG ou WEBP, até 10 MB)"),
    latitude: float | None = Form(None, ge=-90, le=90),
    longitude: float | None = Form(None, ge=-180, le=180),
    endereco: str | None = Form(None, max_length=200, description="Endereço digitado ou obtido pelo mapa"),
    descricao: str | None = Form(None, max_length=500),
    origem: str = Form("app", pattern="^(app|video|carrinho)$"),
):
    data = await foto.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Foto maior que 10 MB.")
    det: Detector = state["detector"]
    try:
        img = det.decode(data)  # re-codificar a partir dos pixels descarta o EXIF (GPS, aparelho)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    rostos = det.blur_faces(img)  # LGPD: borra rostos antes de qualquer armazenamento
    dets = det.detect(img)
    if not dets:
        return JSONResponse(status_code=200, content={
            "ocorrencia": None, "deteccoes": [], "rostos_borrados": rostos,
            "mensagem": "Nenhuma barreira identificada com segurança. Tente outra foto, mais perto e com boa luz."})

    ocorrencia = registrar_ocorrencia(img, dets, origem=origem, latitude=latitude, longitude=longitude,
                                      endereco=endereco, descricao=descricao)
    return {"ocorrencia": ocorrencia, "deteccoes": ocorrencia["deteccoes"], "rostos_borrados": rostos,
            "mensagem": _mensagem(Detector.resumo(dets))}


def registrar_ocorrencia(img, dets, origem: str, latitude=None, longitude=None, endereco=None, descricao=None) -> dict:
    """Salva a foto anotada e grava a ocorrência (usado pela foto do app e pela análise de vídeo)."""
    det: Detector = state["detector"]
    resumo = Detector.resumo(dets)
    protocolo = datetime.now(timezone.utc).strftime("CL-%Y%m%d-") + secrets.token_hex(3).upper()
    arquivo = photos_dir() / f"{protocolo}.jpg"
    ok, buf = cv2.imencode(".jpg", Detector.annotate(img, dets), [cv2.IMWRITE_JPEG_QUALITY, 85])
    arquivo.write_bytes(buf.tobytes())
    ocorrencia = db.insert({
        "protocolo": protocolo, "origem": origem, "tipo": resumo["tipo"], "confianca": resumo["confianca"],
        "prioridade": resumo["prioridade"], "status": resumo["status"], "latitude": latitude,
        "longitude": longitude, "endereco": endereco, "descricao": descricao, "deteccoes": [d.as_dict() for d in dets],
        "foto": arquivo.name, "modelo": det.weights.name,
    })
    integracao_mvp.enviar(ocorrencia)  # replica no MVP do grupo (origem "visao")
    log.info("ocorrencia %s origem=%s tipo=%s conf=%.2f status=%s", protocolo, origem, resumo["tipo"],
             resumo["confianca"], resumo["status"])
    return ocorrencia


# ------------------------------------------------------------------ vídeo com análise ao vivo
@app.post("/videos", tags=["visão"], status_code=201)
async def enviar_video(
    video: UploadFile = File(..., description="Vídeo da calçada (MP4, WEBM, MOV, AVI ou MKV, até 200 MB)"),
    latitude: float | None = Form(None, ge=-90, le=90),
    longitude: float | None = Form(None, ge=-180, le=180),
    endereco: str | None = Form(None, max_length=200),
):
    """Recebe o vídeo e prepara a análise. O navegador acompanha ao vivo em /videos/{id}/ao-vivo."""
    sufixo = Path(video.filename or "").suffix.lower()
    if sufixo not in video_mod.EXTENSOES and not (video.content_type or "").startswith("video/"):
        raise HTTPException(422, "Arquivo não é um vídeo (use MP4, WEBM, MOV, AVI ou MKV).")
    a = video_mod.nova_analise(sufixo if sufixo in video_mod.EXTENSOES else ".mp4", latitude, longitude, endereco)
    tamanho = 0
    with open(a.caminho, "wb") as f:
        while bloco := await video.read(1 << 20):
            tamanho += len(bloco)
            if tamanho > video_mod.MAX_VIDEO:
                f.close()
                a.caminho.unlink(missing_ok=True)
                raise HTTPException(413, "Vídeo maior que 200 MB.")
            f.write(bloco)
    return {"id": a.id, "ao_vivo_url": f"/videos/{a.id}/ao-vivo", "status_url": f"/videos/{a.id}"}


@app.get("/videos/{aid}/ao-vivo", tags=["visão"])
def video_ao_vivo(aid: str, ritmo_real: bool = True):
    """Fluxo MJPEG com cada quadro analisado (caixas, contagem e FPS), na velocidade natural do vídeo."""
    a = video_mod.ANALISES.get(aid)
    if not a:
        raise HTTPException(404, "Análise não encontrada.")
    if a.status == "aguardando":
        return StreamingResponse(video_mod.transmitir(a, registrar_ocorrencia, ritmo_real=ritmo_real),
                                 media_type="multipart/x-mixed-replace; boundary=quadro",
                                 headers={"Cache-Control": "no-store"})
    if a.ultimo_quadro:  # análise já feita: devolve o último quadro
        return Response(a.ultimo_quadro, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    raise HTTPException(409, "Análise em andamento.")


@app.get("/videos/{aid}", tags=["visão"])
def video_status(aid: str):
    a = video_mod.ANALISES.get(aid)
    if not a:
        raise HTTPException(404, "Análise não encontrada.")
    return a.resumo()


def _mensagem(resumo: dict) -> str:
    rotulo = LABELS[resumo["tipo"]].lower()
    if resumo["status"] == "pendente_validacao":
        return f"Possível {rotulo} identificado. Uma pessoa da equipe vai confirmar antes do encaminhamento."
    return f"{LABELS[resumo['tipo']]} identificado. Ocorrência registrada e enviada para triagem."


@app.get("/ocorrencias", tags=["ocorrências"])
def listar(tipo: Tipo | None = None, status: Status | None = None, limite: int = Query(500, ge=1, le=2000)):
    return db.list_(tipo.value if tipo else None, status.value if status else None, limite)


@app.get("/ocorrencias.geojson", tags=["ocorrências"])
def geojson():
    feats = [{"type": "Feature",
              "geometry": {"type": "Point", "coordinates": [o["longitude"], o["latitude"]]},
              "properties": {k: o[k] for k in ("id", "protocolo", "tipo", "confianca", "prioridade", "status", "endereco", "criado_em")}}
             for o in db.list_() if o["latitude"] is not None and o["longitude"] is not None]
    return {"type": "FeatureCollection", "features": feats}


@app.get("/ocorrencias/{oid}", tags=["ocorrências"])
def obter(oid: int):
    o = db.get(oid)
    if not o:
        raise HTTPException(404, "Ocorrência não encontrada.")
    return o


@app.patch("/ocorrencias/{oid}", tags=["ocorrências"])
def atualizar(oid: int, body: Atualizacao):
    """Validação humana: confirmar, rejeitar, corrigir o tipo ou marcar como resolvida."""
    if not db.get(oid):
        raise HTTPException(404, "Ocorrência não encontrada.")
    fields = {k: (v.value if isinstance(v, Enum) else v) for k, v in body.model_dump(exclude_none=True).items()}
    return db.update(oid, fields)


@app.get("/ocorrencias/{oid}/foto", tags=["ocorrências"])
def foto(oid: int):
    nome = db.foto_path(oid)
    if not nome or not (photos_dir() / nome).exists():
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(photos_dir() / nome, media_type="image/jpeg")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
