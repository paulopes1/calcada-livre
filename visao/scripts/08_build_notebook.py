"""Gera e EXECUTA o notebook de análise (notebooks/visao_calcada_livre.ipynb), salvando as saídas.

O notebook não treina de novo: ele lê os artefatos do pipeline (dataset e results/) e mostra,
em uma narrativa só, os dados, o treino, as métricas, os exemplos e a inferência ao vivo.

Uso:  python scripts/08_build_notebook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("# Calçada Livre · Visão Computacional\n"
       "**FIAP · Global Solution 2026.2 · Applied Computer Vision** — Carlos Ganzerli (RM 99840), "
       "Paulo Lopes (RM 551137), Lucas Bandeira (RM 98640), Gustavo Melo (RM 98809).\n\n"
       "Detector YOLO26n treinado de forma customizada para três barreiras de acessibilidade em calçadas: "
       "**buraco**, **obstáculo** e **piso quebrado**. Este notebook documenta os dados, o treino, a avaliação e a "
       "inferência. Os scripts numerados em `scripts/` reproduzem cada etapa."),
    code("%config InlineBackend.figure_formats = ['jpeg']\nimport json, os, sys\nfrom pathlib import Path\n"
         "import pandas as pd, matplotlib.pyplot as plt, cv2\nplt.rcParams['figure.dpi'] = 72\n"
         "ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
         "sys.path.insert(0, str(ROOT / 'scripts'))\nfrom common import DATASET, class_names\n"
         "import torch, ultralytics\nprint('PyTorch', torch.__version__, '| CUDA:', torch.cuda.is_available(),"
         " torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')\nprint('Ultralytics', ultralytics.__version__)\n"
         "print('Classes:', class_names())"),
    md("## 1. Dataset customizado\nDois datasets públicos (MIT) com visão de pedestre foram remapeados para a "
       "taxonomia do projeto (`configs/classes.yaml`), limpos e deduplicados por pHash antes da divisão 80/10/10."),
    code("stats = json.loads((ROOT/'results'/'dataset_stats.json').read_text(encoding='utf-8'))\n"
         "print({k: v for k, v in stats.items() if k != 'splits'})\n"
         "rows = []\nfor s, v in stats['splits'].items():\n"
         "    rows.append({'split': s, 'imagens': v['images'], 'fundo (sem barreira)': v['background'], **v['instances']})\n"
         "pd.DataFrame(rows).set_index('split')"),
    code("img = plt.imread(ROOT/'results'/'figuras'/'dataset_distribuicao.png')\nplt.figure(figsize=(10,4)); plt.imshow(img); plt.axis('off');"),
    code("img = plt.imread(ROOT/'results'/'figuras'/'dataset_amostras.jpg')\nplt.figure(figsize=(14,7)); plt.imshow(img); plt.axis('off');"),
    md("## 2. Treino (fine-tuning a partir do COCO)\nCurvas de perda e de métricas de validação por época."),
    code("df = pd.read_csv(ROOT/'results'/'treino'/'yolo26n_calcada'/'results.csv'); df.columns = [c.strip() for c in df.columns]\n"
         "fig, ax = plt.subplots(1, 3, figsize=(16, 4))\n"
         "for c in ['train/box_loss','train/cls_loss','val/box_loss','val/cls_loss']:\n"
         "    if c in df: ax[0].plot(df['epoch'], df[c], label=c)\nax[0].set_title('Perdas'); ax[0].legend()\n"
         "for c in ['metrics/mAP50(B)','metrics/mAP50-95(B)']: ax[1].plot(df['epoch'], df[c], label=c)\nax[1].set_title('mAP (validação)'); ax[1].legend()\n"
         "for c in ['metrics/precision(B)','metrics/recall(B)']: ax[2].plot(df['epoch'], df[c], label=c)\nax[2].set_title('Precisão e revocação (validação)'); ax[2].legend()\n"
         "plt.tight_layout(); print(json.loads((ROOT/'results'/'treino'/'yolo26n_calcada'/'train_info.json').read_text()))"),
    md("## 3. Avaliação do modelo final no conjunto de teste\nImagens que o modelo nunca viu. IoU 0,5 para mAP50; 0,5–0,95 para mAP50-95."),
    code("m = json.loads((ROOT/'results'/'calcada_yolo26n'/'metrics.json').read_text(encoding='utf-8'))\n"
         "print('Geral:', m['geral'])\nprint('Velocidade:', m['velocidade'])\npd.DataFrame(m['por_classe']).T"),
    code("fig, ax = plt.subplots(1, 2, figsize=(16, 6))\n"
         "ax[0].imshow(plt.imread(ROOT/'results'/'figuras'/'matriz_confusao.png')); ax[0].axis('off')\n"
         "ax[1].imshow(plt.imread(ROOT/'results'/'figuras'/'curva_pr.png')); ax[1].axis('off'); plt.tight_layout()"),
    md("### Comparação de arquiteturas (mesmo dataset, mesma receita)"),
    code("print((ROOT/'results'/'comparacao.md').read_text(encoding='utf-8'))"),
    md("## 4. Exemplos de acerto e de erro (gabarito × predição)"),
    code("ex = sorted((ROOT/'results'/'calcada_yolo26n'/'exemplos').glob('*.jpg'))\n"
         "for p in ex:\n    plt.figure(figsize=(14, 5)); plt.imshow(cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)); plt.title(p.stem); plt.axis('off')"),
    md("## 5. Calçadas brasileiras: teste fora da distribuição e adaptação de domínio\n"
       "Vídeos reais da Bela Vista, São Paulo (Wikimedia Commons, CC BY 3.0). Cada vídeo foi dividido no tempo: início "
       "para adaptação (fine-tuning), intervalo descartado e final como **teste brasileiro**, nunca usado no treino. "
       "O modelo só treinado com datasets estrangeiros quase não reconhecia o piso quebrado brasileiro; a tabela mostra "
       "o efeito da adaptação nos dois conjuntos de teste."),
    code("ad = json.loads((ROOT/'results'/'adaptacao_br.json').read_text(encoding='utf-8'))\n"
         "print({k: ad[k] for k in ('quadros_adaptacao','oversampling','quadros_teste_brasil','epocas')})\n"
         "rows = []\nfor fase in ('antes','depois'):\n    for conj in ('teste_original','teste_brasil'):\n"
         "        rows.append({'modelo': fase + ' da adaptação', 'teste': conj, **ad[fase][conj]['geral']})\n"
         "pd.DataFrame(rows)"),
    code("img = plt.imread(ROOT/'results'/'figuras'/'adaptacao_antes_depois.jpg')\nplt.figure(figsize=(14,16)); plt.imshow(img); plt.axis('off');"),
    code("img = plt.imread(ROOT/'results'/'figuras'/'sao_paulo_quadros.jpg')\nplt.figure(figsize=(16,9)); plt.imshow(img); plt.axis('off'); plt.title('Modelo final no teste brasileiro');"),
    md("## 6. Integração com o MVP: chamada real ao endpoint `/detectar`"),
    code("import tempfile\nos.environ['DB_PATH'] = str(Path(tempfile.mkdtemp())/'nb.db')\nos.environ['PHOTOS_DIR'] = str(Path(tempfile.mkdtemp()))\n"
         "os.chdir(ROOT)\nfrom fastapi.testclient import TestClient\nfrom api.main import app\n"
         "foto = sorted((ROOT/'samples').glob('buraco_*.jpg'))[0]\n"
         "with TestClient(app) as c:\n"
         "    r = c.post('/detectar', files={'foto': (foto.name, foto.read_bytes(), 'image/jpeg')}, data={'latitude': -23.5614, 'longitude': -46.6559})\n"
         "    body = r.json(); print(r.status_code, body['mensagem'])\n"
         "    o = body['ocorrencia']; print({k: o[k] for k in ('protocolo','tipo','confianca','prioridade','status')})\n"
         "    import numpy as np\n    im = cv2.imdecode(np.frombuffer(c.get(o['foto_url']).content, np.uint8), cv2.IMREAD_COLOR)\n"
         "plt.figure(figsize=(8,6)); plt.imshow(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)); plt.axis('off'); plt.title('Foto guardada pela API (anotada, sem EXIF)');"),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                 "language_info": {"name": "python"}})
out = ROOT / "notebooks" / "visao_calcada_livre.ipynb"
out.parent.mkdir(exist_ok=True)
ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(out.parent)}})
nbf.write(nb, out)
print("Notebook executado e salvo em", out)
