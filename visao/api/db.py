"""Persistência das ocorrências em SQLite (arquivo local, sem servidor).

O esquema segue o contrato único da "ocorrência" do MVP Calçada Livre, compartilhado por todos os
componentes (carrinho, visão, RPA, Big Data, assistente e mapa). Nenhum dado pessoal é guardado:
não há nome, e-mail, telefone ou IP de quem reportou.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = """
CREATE TABLE IF NOT EXISTS ocorrencias (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo     TEXT UNIQUE NOT NULL,
    origem        TEXT NOT NULL,              -- app | video | carrinho
    tipo          TEXT NOT NULL,              -- buraco | obstaculo | piso_quebrado
    confianca     REAL NOT NULL,
    prioridade    TEXT NOT NULL,              -- baixa | media | alta
    status        TEXT NOT NULL,              -- pendente_validacao | aberta | validada | rejeitada | resolvida
    latitude      REAL,
    longitude     REAL,
    endereco      TEXT,                       -- endereço digitado ou obtido pelo mapa
    descricao     TEXT,
    deteccoes     TEXT NOT NULL,              -- JSON com todas as caixas
    foto          TEXT NOT NULL,              -- arquivo da foto anotada (EXIF removido, rostos borrados)
    modelo        TEXT NOT NULL,
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status ON ocorrencias(status);
CREATE INDEX IF NOT EXISTS idx_tipo ON ocorrencias(tipo);
"""

_lock = threading.Lock()


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", ROOT / "storage" / "ocorrencias.db"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def session():
    """Abre a conexão, faz commit no fim (ou rollback em erro) e sempre fecha o arquivo."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    novo = not path.exists()  # o arquivo pode ter sido apagado com a API no ar (limpeza da demonstração)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    if novo:
        con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init() -> None:
    with session() as con:
        con.executescript(SCHEMA)
        # migração: bancos criados antes da coluna "endereco" ganham a coluna sem perder dados
        cols = {r["name"] for r in con.execute("PRAGMA table_info(ocorrencias)")}
        if "endereco" not in cols:
            con.execute("ALTER TABLE ocorrencias ADD COLUMN endereco TEXT")


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["deteccoes"] = json.loads(d["deteccoes"])
    d["foto_url"] = f"/ocorrencias/{d['id']}/foto"
    d.pop("foto", None)
    return d


def _get(con: sqlite3.Connection, oid: int) -> dict | None:
    row = con.execute("SELECT * FROM ocorrencias WHERE id = ?", (oid,)).fetchone()
    return row_to_dict(row) if row else None


def insert(o: dict) -> dict:
    with _lock, session() as con:
        ts = now()
        cur = con.execute(
            """INSERT INTO ocorrencias (protocolo, origem, tipo, confianca, prioridade, status, latitude,
               longitude, endereco, descricao, deteccoes, foto, modelo, criado_em, atualizado_em)
               VALUES (:protocolo, :origem, :tipo, :confianca, :prioridade, :status, :latitude, :longitude,
               :endereco, :descricao, :deteccoes, :foto, :modelo, :ts, :ts)""",
            {"endereco": None, **o, "deteccoes": json.dumps(o["deteccoes"], ensure_ascii=False), "ts": ts},
        )
        return _get(con, cur.lastrowid)


def get(oid: int) -> dict | None:
    with session() as con:
        return _get(con, oid)


def foto_path(oid: int) -> str | None:
    with session() as con:
        row = con.execute("SELECT foto FROM ocorrencias WHERE id = ?", (oid,)).fetchone()
        return row["foto"] if row else None


def list_(tipo: str | None = None, status: str | None = None, limit: int = 500) -> list[dict]:
    q, args = "SELECT * FROM ocorrencias WHERE 1=1", []
    if tipo:
        q, args = q + " AND tipo = ?", args + [tipo]
    if status:
        q, args = q + " AND status = ?", args + [status]
    q += " ORDER BY id DESC LIMIT ?"
    with session() as con:
        return [row_to_dict(r) for r in con.execute(q, args + [limit]).fetchall()]


ALLOWED_UPDATE = {"status", "tipo", "prioridade", "descricao", "endereco", "latitude", "longitude"}


def update(oid: int, fields: dict) -> dict | None:
    fields = {k: v for k, v in fields.items() if k in ALLOWED_UPDATE}  # só colunas permitidas
    with _lock, session() as con:
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields) + ", atualizado_em = ?"
            con.execute(f"UPDATE ocorrencias SET {sets} WHERE id = ?", [*fields.values(), now(), oid])
        return _get(con, oid)
