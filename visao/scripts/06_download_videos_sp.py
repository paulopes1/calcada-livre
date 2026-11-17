"""Etapa 6 — baixa vídeos reais de calçadas de São Paulo (Wikimedia Commons, licença CC BY 3.0).

Esses vídeos NÃO entram no treino: servem como teste fora da distribuição (cidade brasileira, câmera
e época diferentes dos datasets de treino) e como material do vídeo de demonstração.
Atribuição obrigatória (CC BY 3.0): ver docs/CREDITOS.md.

Uso:  python scripts/06_download_videos_sp.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA  # noqa: E402

VIDEOS = [  # título no Wikimedia Commons (autor: Daniel Fraga, exceto quando indicado)
    "Buraco sem tampa na calçada.webm",
    "Calçada danificada na rua Rocha, 206 (Bela Vista).webm",
    "Calçada danificada na alameda Ribeirão Preto, 362 (Bela Vista).webm",
    "Calçada danificada na alameda Ribeirão Preto, 314 (Bela Vista).webm",
    'Calçada abandonada na rua Cardeal Leme - "rua da Feira" (Bela Vista).webm',
    "Madeira jogada na calçada.webm",
    "Estacionamento da Prosport bloqueando a calçada.webm",
    "Acesso danificado acumulando água na rua São Carlos do Pinhal.webm",
    "Nova lixeira na calçada atrapalha pedestres.webm",  # autor: Videojournalisms
]
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "calcada-livre-edu/1.0 (projeto academico de visao computacional)"}


def main() -> None:
    out = DATA / "videos_sp"
    out.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update(HEADERS)
    for title in VIDEOS:
        dest = out / title.replace('"', "").replace(",", "")
        if dest.exists():
            print("ok (já existe):", dest.name)
            continue
        info = s.get(API, params={"action": "query", "prop": "imageinfo", "iiprop": "url", "format": "json",
                                  "titles": "File:" + title}, timeout=30).json()
        url = next(iter(info["query"]["pages"].values()))["imageinfo"][0]["url"]
        for attempt in range(6):
            with s.get(url, stream=True, timeout=120) as r:
                if r.status_code == 429:  # limite de taxa da Wikimedia: espera crescente
                    time.sleep(15 * (attempt + 1))
                    continue
                r.raise_for_status()
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.replace(dest)
                break
        else:
            print("falhou após várias tentativas:", title)
            continue
        print(f"baixado: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        time.sleep(5)  # respeita os limites de uso da Wikimedia


if __name__ == "__main__":
    main()
