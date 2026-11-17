"""Apaga todas as ocorrências e fotos guardadas pela API (útil antes de gravar uma demonstração).

Pode rodar com a API no ar: o banco é recriado vazio na próxima requisição.
Uso:  python scripts/limpar_ocorrencias.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("DB_PATH", ROOT / "storage" / "ocorrencias.db"))
FOTOS = Path(os.environ.get("PHOTOS_DIR", ROOT / "storage" / "fotos"))


def main() -> None:
    n_fotos = len(list(FOTOS.glob("*.jpg"))) if FOTOS.exists() else 0
    if DB.exists():
        DB.unlink()
    if FOTOS.exists():
        shutil.rmtree(FOTOS)
    print(f"Histórico apagado: banco de ocorrências e {n_fotos} foto(s). Atualize a página do MVP (F5).")


if __name__ == "__main__":
    sys.exit(main())
