"""Integração com a API central do MVP do grupo (POST /api/ocorrencias).

Cada ocorrência registrada pela visão é replicada no MVP com origem "visao", no formato que a
automação de triagem (RPA) aceita. As regras abaixo espelham as do robô: coordenada dentro de
São Paulo, tipo da lista do MVP, link da foto e confiança mínima de 0,5. O que não passa nessas
regras não é enviado (fica só aqui, no painel da zeladoria da visão) e o motivo vai para o log.

Configuração por variáveis de ambiente:
  MVP_API_URL        endereço do MVP (ex.: https://calcadalivre.exemplo.com). Sem ela, nada é enviado.
  VISAO_URL_PUBLICA  endereço público desta API, usado para montar o link absoluto da foto
                     (padrão: http://127.0.0.1:8000).
"""
from __future__ import annotations

import logging
import os
import threading

import requests

log = logging.getLogger("calcada.visao.mvp")

# Classes da visão -> tipos aceitos pelo MVP (piso quebrado não existe lá: vai como "outro" + descrição)
TIPO_MVP = {"buraco": "buraco", "obstaculo": "obstaculo", "piso_quebrado": "outro"}
NOME = {"buraco": "Buraco", "obstaculo": "Obstáculo", "piso_quebrado": "Piso quebrado"}
CONFIANCA_MINIMA = 0.5
LAT_MIN, LAT_MAX = -24.01, -23.35  # mesma caixa de São Paulo usada pela triagem
LON_MIN, LON_MAX = -46.83, -46.36


def url_destino() -> str | None:
    base = (os.environ.get("MVP_API_URL") or "").strip().rstrip("/")
    if not base:
        return None
    if base.endswith("/api/ocorrencias"):
        return base
    return f"{base}/ocorrencias" if base.endswith("/api") else f"{base}/api/ocorrencias"


def montar(oc: dict) -> tuple[dict | None, str | None]:
    """Converte a ocorrência da visão no corpo do POST do MVP. Retorna (corpo, None) ou (None, motivo)."""
    lat, lon = oc.get("latitude"), oc.get("longitude")
    if lat is None or lon is None:
        return None, "sem_localizacao"
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None, "fora_de_sao_paulo"
    if oc["tipo"] not in TIPO_MVP:
        return None, "tipo_desconhecido"
    if (oc.get("confianca") or 0) < CONFIANCA_MINIMA:
        return None, "baixa_confianca"
    base = os.environ.get("VISAO_URL_PUBLICA", "http://127.0.0.1:8000").rstrip("/")
    partes = [f"{NOME[oc['tipo']]} detectado por visão computacional ({oc.get('modelo')}, "
              f"{oc['confianca']:.0%} de confiança). Protocolo da visão: {oc['protocolo']}."]
    if oc.get("endereco"):
        partes.append(f"Endereço: {oc['endereco']}.")
    if oc.get("descricao"):
        partes.append(f"Comentário: {oc['descricao']}")
    return {
        "tipo": TIPO_MVP[oc["tipo"]],
        "latitude": round(float(lat), 6),
        "longitude": round(float(lon), 6),
        "origem": "visao",
        "descricao": " ".join(partes)[:1000],
        "foto_url": f"{base}/ocorrencias/{oc['id']}/foto",
        "confianca": round(float(oc["confianca"]), 4),
    }, None


def _postar(url: str, corpo: dict, protocolo: str) -> None:
    try:
        r = requests.post(url, json=corpo, timeout=5)
        r.raise_for_status()
        log.info("ocorrencia %s replicada no MVP (id %s)", protocolo, r.json().get("id"))
    except (requests.RequestException, ValueError) as e:
        log.warning("Não foi possível replicar %s no MVP: %s", protocolo, e)


def enviar(oc: dict) -> threading.Thread | None:
    """Replica em segundo plano (não atrasa a resposta nem o vídeo ao vivo). Falha não derruba o registro."""
    url = url_destino()
    if not url:
        return None
    corpo, motivo = montar(oc)
    if corpo is None:
        log.info("ocorrencia %s não enviada ao MVP: %s", oc["protocolo"], motivo)
        return None
    t = threading.Thread(target=_postar, args=(url, corpo, oc["protocolo"]), daemon=True)
    t.start()
    return t
