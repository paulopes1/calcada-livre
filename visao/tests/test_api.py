"""Testes automatizados da API de Visão (rodar com:  pytest -q).

Usam o modelo treinado de verdade e imagens de exemplo do conjunto de teste (samples/).
Banco e fotos vão para uma pasta temporária, sem sujar o ambiente.
"""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
MODEL = ROOT / "models" / "calcada_yolo26n.pt"

pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="modelo treinado ausente (rode scripts/03_train.py)")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    mp = pytest.MonkeyPatch()
    mp.setenv("DB_PATH", str(tmp / "test.db"))
    mp.setenv("PHOTOS_DIR", str(tmp / "fotos"))
    mp.setenv("VIDEOS_DIR", str(tmp / "videos"))
    from api.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def jpg_bytes(path: Path) -> bytes:
    return path.read_bytes()


def sample(prefix: str) -> Path:
    files = sorted(SAMPLES.glob(f"{prefix}*.jpg"))
    assert files, f"sem amostras '{prefix}' em samples/"
    return files[0]


def test_saude(client):
    r = client.get("/saude")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["classes"]) == {"buraco", "obstaculo", "piso_quebrado"}


@pytest.mark.parametrize("prefix,esperado", [("buraco", "buraco"), ("obstaculo", "obstaculo"),
                                             ("piso_quebrado", "piso_quebrado")])
def test_detectar_cria_ocorrencia_com_tipo(client, prefix, esperado):
    r = client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample(prefix)), "image/jpeg")},
                    data={"latitude": "-23.5614", "longitude": "-46.6559", "origem": "app"})
    assert r.status_code == 201, r.text
    o = r.json()["ocorrencia"]
    assert o["tipo"] == esperado
    assert o["status"] in {"aberta", "pendente_validacao"}
    assert o["protocolo"].startswith("CL-")
    assert 0 < o["confianca"] <= 1
    assert client.get(o["foto_url"]).headers["content-type"] == "image/jpeg"


def test_endereco_digitado_e_salvo_e_corrigido(client):
    r = client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample("piso_quebrado")), "image/jpeg")},
                    data={"endereco": "Rua Rocha, 206 - Bela Vista - São Paulo", "latitude": "-23.5598", "longitude": "-46.6463"})
    assert r.status_code == 201, r.text
    o = r.json()["ocorrencia"]
    assert o["endereco"] == "Rua Rocha, 206 - Bela Vista - São Paulo"
    r = client.patch(f"/ocorrencias/{o['id']}", json={"endereco": "Rua Rocha, 210 - Bela Vista - São Paulo"})
    assert r.status_code == 200 and r.json()["endereco"].startswith("Rua Rocha, 210")
    feats = client.get("/ocorrencias.geojson").json()["features"]
    assert any(f["properties"]["endereco"] for f in feats)


def test_limpeza_com_api_no_ar_recria_banco_vazio(client):
    """Apagar o banco (limpeza antes de uma demonstração) não pode derrubar a API."""
    import os
    client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample("obstaculo")), "image/jpeg")})
    Path(os.environ["DB_PATH"]).unlink()
    assert client.get("/ocorrencias").json() == []
    r = client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample("obstaculo")), "image/jpeg")})
    assert r.status_code == 201 and len(client.get("/ocorrencias").json()) == 1


def test_imagem_sem_barreira_nao_cria_ocorrencia(client):
    blank = np.full((480, 640, 3), 200, np.uint8)  # imagem lisa, sem nada
    ok, buf = cv2.imencode(".jpg", blank)
    r = client.post("/detectar", files={"foto": ("x.jpg", buf.tobytes(), "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["ocorrencia"] is None


def test_arquivo_invalido_retorna_422(client):
    r = client.post("/detectar", files={"foto": ("x.jpg", b"isto nao e uma imagem", "image/jpeg")})
    assert r.status_code == 422


def test_coordenada_invalida_retorna_422(client):
    r = client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample("buraco")), "image/jpeg")},
                    data={"latitude": "123"})
    assert r.status_code == 422


def test_exif_gps_e_removido(client, tmp_path):
    """LGPD: a foto guardada não pode carregar a localização GPS gravada pelo celular."""
    img = Image.open(sample("buraco"))
    exif = Image.Exif()
    exif[0x8825] = {1: "S", 2: (23.0, 33.0, 41.0), 3: "W", 4: (46.0, 39.0, 21.0)}  # GPSInfo
    exif[0x0110] = "Celular de Teste"  # modelo do aparelho
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    r = client.post("/detectar", files={"foto": ("gps.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 201
    saved = Image.open(io.BytesIO(client.get(r.json()["ocorrencia"]["foto_url"]).content))
    assert len(saved.getexif()) == 0


def test_validacao_humana_e_filtros(client):
    r = client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample("obstaculo")), "image/jpeg")},
                    data={"latitude": "-23.56", "longitude": "-46.65"})
    oid = r.json()["ocorrencia"]["id"]
    r = client.patch(f"/ocorrencias/{oid}", json={"status": "validada", "tipo": "obstaculo"})
    assert r.status_code == 200 and r.json()["status"] == "validada"
    assert client.patch(f"/ocorrencias/{oid}", json={"status": "inexistente"}).status_code == 422
    assert client.patch("/ocorrencias/999999", json={"status": "validada"}).status_code == 404
    assert all(o["status"] == "validada" for o in client.get("/ocorrencias?status=validada").json())
    gj = client.get("/ocorrencias.geojson").json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) >= 1


# ------------------------------------------------------------------ vídeo com análise ao vivo
def video_de_teste(tmp_path: Path) -> Path:
    """Vídeo curto (MP4) feito com uma foto de obstáculo do conjunto de teste, com leve movimento."""
    img = cv2.imread(str(sample("obstaculo")))
    h, w = img.shape[:2]
    caminho = tmp_path / "calcada.mp4"
    out = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(24):
        out.write(np.roll(img, i * 2, axis=1))
    out.release()
    return caminho


def test_video_analisado_ao_vivo_vira_ocorrencias(client, tmp_path):
    import os
    v = video_de_teste(tmp_path)
    r = client.post("/videos", files={"video": ("calcada.mp4", v.read_bytes(), "video/mp4")},
                    data={"endereco": "Rua Treze de Maio, 500 - Bela Vista", "latitude": "-23.5598", "longitude": "-46.6512"})
    assert r.status_code == 201, r.text
    j = r.json()
    with client.stream("GET", j["ao_vivo_url"] + "?ritmo_real=false") as s:
        assert s.headers["content-type"].startswith("multipart/x-mixed-replace")
        partes = sum(ch.count(b"--quadro") for ch in s.iter_bytes())
    assert partes == 24  # todos os quadros analisados e transmitidos
    st = client.get(j["status_url"]).json()
    assert st["status"] == "concluida" and st["quadros"] == 24
    assert st["contagem"]["obstaculo"] >= 1 and len(st["ocorrencias"]) >= 1
    o = client.get(f"/ocorrencias/{st['ocorrencias'][0]['id']}").json()
    assert o["origem"] == "video" and o["tipo"] == "obstaculo" and o["endereco"].startswith("Rua Treze de Maio")
    assert not any(Path(os.environ["VIDEOS_DIR"]).glob("*"))  # LGPD: vídeo original apagado
    assert client.get(j["ao_vivo_url"]).headers["content-type"] == "image/jpeg"  # reabrir mostra o último quadro


def test_video_invalido_e_analise_inexistente(client):
    r = client.post("/videos", files={"video": ("notas.txt", b"isto nao e video", "text/plain")})
    assert r.status_code == 422
    assert client.get("/videos/naoexiste").status_code == 404
    assert client.get("/videos/naoexiste/ao-vivo").status_code == 404


# ------------------------------------------------------------------ integração com o MVP do grupo
def test_formato_aceito_pela_triagem_do_mvp(monkeypatch):
    from api import integracao_mvp as mvp
    monkeypatch.setenv("VISAO_URL_PUBLICA", "https://visao.exemplo.com/")
    oc = {"id": 7, "protocolo": "CL-20261117-ABC123", "tipo": "piso_quebrado", "confianca": 0.82,
          "latitude": -23.5614, "longitude": -46.6559, "endereco": "Rua Rocha, 206", "descricao": None,
          "modelo": "calcada_yolo26n.pt"}
    corpo, motivo = mvp.montar(oc)
    assert motivo is None
    assert corpo["origem"] == "visao" and corpo["tipo"] == "outro" and "Piso quebrado" in corpo["descricao"]
    assert corpo["foto_url"] == "https://visao.exemplo.com/ocorrencias/7/foto" and corpo["confianca"] == 0.82
    assert mvp.montar({**oc, "tipo": "buraco"})[0]["tipo"] == "buraco"
    assert mvp.montar({**oc, "confianca": 0.49}) == (None, "baixa_confianca")
    assert mvp.montar({**oc, "latitude": -22.9, "longitude": -43.2}) == (None, "fora_de_sao_paulo")
    assert mvp.montar({**oc, "latitude": None}) == (None, "sem_localizacao")
    for base in ("https://mvp.exemplo.com", "https://mvp.exemplo.com/api", "https://mvp.exemplo.com/api/ocorrencias/"):
        monkeypatch.setenv("MVP_API_URL", base)
        assert mvp.url_destino() == "https://mvp.exemplo.com/api/ocorrencias"


def test_deteccao_e_replicada_no_mvp(client, monkeypatch):
    import threading
    from api import integracao_mvp as mvp
    recebido, chegou = {}, threading.Event()

    def falso_post(url, corpo, protocolo):
        recebido.update(url=url, corpo=corpo)
        chegou.set()

    monkeypatch.setenv("MVP_API_URL", "https://mvp.exemplo.com")
    monkeypatch.setattr(mvp, "_postar", falso_post)
    r = client.post("/detectar", files={"foto": ("f.jpg", jpg_bytes(sample("buraco")), "image/jpeg")},
                    data={"latitude": "-23.5614", "longitude": "-46.6559"})
    o = r.json()["ocorrencia"]
    if o["confianca"] < mvp.CONFIANCA_MINIMA:
        pytest.skip("amostra abaixo da confiança mínima do MVP")
    assert chegou.wait(5)
    assert recebido["url"] == "https://mvp.exemplo.com/api/ocorrencias"
    assert recebido["corpo"]["origem"] == "visao" and recebido["corpo"]["tipo"] == "buraco"
    assert recebido["corpo"]["foto_url"].endswith(f"/ocorrencias/{o['id']}/foto")
