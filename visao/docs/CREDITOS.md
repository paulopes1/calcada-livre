# Créditos, fontes de dados e licenças

Todos os dados usados são públicos e têm licença que permite uso e redistribuição com atribuição.
Nenhuma imagem de terceiros é redistribuída neste repositório além das poucas amostras em `samples/`
(derivadas dos datasets MIT abaixo) usadas nos testes automatizados.

## Datasets de treino

| Dataset | Origem | Licença | Uso no projeto |
|---|---|---|---|
| **Unified Obstacles Dataset** (projeto AssistEye) | [huggingface.co/datasets/Dderedor/obstacles_on_the_road](https://huggingface.co/datasets/Dderedor/obstacles_on_the_road), que une *Urban Community Issues* (Kaggle) e *Obstacles Avoidance Assistance for Visually Impaired* (Mendeley Data) | MIT | buraco (pothole, open_manhole), piso_quebrado (hole/trincas), obstaculo (waste_container, pole) |
| **Pothole Detection Dataset** (rupesh002) | [huggingface.co/datasets/rupesh002/pothole-detection-dataset](https://huggingface.co/datasets/rupesh002/pothole-detection-dataset) | MIT | buraco (reforço da classe; imagens com caixa > 70% da foto descartadas) |
| **ROD-Dataset: Real-Time Obstacle Detection** (Amirkabir University of Technology) | [huggingface.co/datasets/Abtinzandi/Obstacle-Detection-Dataset-YOLO](https://huggingface.co/datasets/Abtinzandi/Obstacle-Detection-Dataset-YOLO) | MIT | obstaculo (lixeira, poste, cone, cavalete, vaso, caixa elétrica, banco, hidrante, paraciclo, cadeira) + imagens de fundo |

## Vídeos de calçadas de São Paulo (adaptação de domínio e teste brasileiro)

Quadros do início de cada vídeo foram anotados pela equipe e usados no fine-tuning de adaptação; quadros do
final de cada vídeo (separados no tempo) formam o teste brasileiro e nunca entram no treino. Fora as figuras de
resultados em `results/figuras/` (com esta atribuição), os quadros não são redistribuídos: o repositório guarda só as
anotações (`configs/anotacoes_sp.json`) e os scripts que extraem os quadros dos vídeos originais.

Wikimedia Commons, licença **Creative Commons Atribuição 3.0 (CC BY 3.0)**:

| Vídeo | Autor |
|---|---|
| [Buraco sem tampa na calçada](https://commons.wikimedia.org/wiki/File:Buraco_sem_tampa_na_cal%C3%A7ada.webm) | Daniel Fraga |
| [Calçada danificada na rua Rocha, 206 (Bela Vista)](https://commons.wikimedia.org/wiki/File:Cal%C3%A7ada_danificada_na_rua_Rocha,_206_(Bela_Vista).webm) | Daniel Fraga |
| [Calçada danificada na alameda Ribeirão Preto, 362 (Bela Vista)](https://commons.wikimedia.org/wiki/File:Cal%C3%A7ada_danificada_na_alameda_Ribeir%C3%A3o_Preto,_362_(Bela_Vista).webm) | Daniel Fraga |
| [Calçada danificada na alameda Ribeirão Preto, 314 (Bela Vista)](https://commons.wikimedia.org/wiki/File:Cal%C3%A7ada_danificada_na_alameda_Ribeir%C3%A3o_Preto,_314_(Bela_Vista).webm) | Daniel Fraga |
| [Calçada abandonada na rua Cardeal Leme - "rua da Feira" (Bela Vista)](https://commons.wikimedia.org/wiki/File:Cal%C3%A7ada_abandonada_na_rua_Cardeal_Leme_-_%22rua_da_Feira%22_(Bela_Vista).webm) | Daniel Fraga |
| [Madeira jogada na calçada](https://commons.wikimedia.org/wiki/File:Madeira_jogada_na_cal%C3%A7ada.webm) | Daniel Fraga |
| [Estacionamento da Prosport bloqueando a calçada](https://commons.wikimedia.org/wiki/File:Estacionamento_da_Prosport_bloqueando_a_cal%C3%A7ada.webm) | Daniel Fraga |
| [Acesso danificado acumulando água na rua São Carlos do Pinhal](https://commons.wikimedia.org/wiki/File:Acesso_danificado_acumulando_%C3%A1gua_na_rua_S%C3%A3o_Carlos_do_Pinhal.webm) | Daniel Fraga |
| [Nova lixeira na calçada atrapalha pedestres](https://commons.wikimedia.org/wiki/File:Nova_lixeira_na_cal%C3%A7ada_atrapalha_pedestres.webm) | Videojournalisms |

A imagem de exemplo da página do MVP (`api/static/img/exemplo-deteccao.jpg`) é um quadro do vídeo de
Videojournalisms, com a detecção do modelo desenhada e rostos e placas borrados.

Nos trechos usados no vídeo de demonstração, os quadros foram processados pelo detector (caixas e
painel sobrepostos) e rostos/placas foram borrados automaticamente.

## Software e modelos

* [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) (AGPL-3.0) — pesos pré-treinados YOLO26n e YOLO11n (COCO).
* [PyTorch](https://pytorch.org/) (BSD-3), [OpenCV](https://opencv.org/) (Apache-2.0), [FastAPI](https://fastapi.tiangolo.com/) (MIT),
  [Leaflet](https://leafletjs.com/) (BSD-2), mapas © colaboradores do [OpenStreetMap](https://www.openstreetmap.org/copyright) (ODbL).
* Rastreamento multiobjeto: ByteTrack (Zhang et al., 2022), implementação do Ultralytics.
