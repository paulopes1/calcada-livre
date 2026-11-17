# Calçada Livre

**FIAP · Global Solution 2026.2 · Desafio CitizenTech · Engenharia de Software (4ES)**

Mapa colaborativo de barreiras de acessibilidade nas calçadas: o cidadão fotografa o problema, a visão
computacional identifica o tipo de barreira e a ocorrência entra no mapa para triagem e zeladoria.

| Integrante | RM |
|---|---|
| Carlos Ganzerli | 99840 |
| Paulo Lopes | 551137 |
| Lucas Bandeira | 98640 |
| Gustavo Melo | 98809 |

## Ficha Técnica do MVP

| Campo | Calçada Livre |
|---|---|
| **Nome** | Calçada Livre: mapa colaborativo de barreiras nas calçadas |
| **Cidadão e território** | Pessoas com deficiência, idosos e quem circula com carrinho de bebê; piloto em São Paulo (SP) |
| **Problema, em uma frase** | Pessoas com mobilidade reduzida deixam de sair de casa ou se machucam porque não sabem quais calçadas têm barreiras, e a prefeitura não tem um mapa atualizado delas. |
| **Proposta de valor** | O cidadão reporta a barreira com uma foto; a visão computacional identifica o tipo, a ocorrência entra no mapa e segue para triagem e zeladoria. |
| **Componentes** | Carrinho inspetor · Visão computacional · Assistente LLM + RAG · Triagem automática · Pipeline de dados · Deploy seguro · Pitch |
| **Fontes de dados** | Datasets públicos de obstáculos e buracos; vídeos de calçadas de SP (Wikimedia Commons); SP156, Open-Meteo e IBGE |
| **Modelos de IA** | YOLO26n customizado (3 classes) + ByteTrack; LLM local com RAG/LoRA |
| **URL e repositório** | Visão computacional: <https://github.com/paulopes1/calcada-livre> · MVP do grupo (site, API e DevOps): <https://github.com/CarlosGanzerli/calcada-livre> |
| **Indicadores de impacto** | Barreiras mapeadas, % resolvidas, dias até a resolução, km de rota acessível |
| **ODS** | 11 (metas 11.2 e 11.7), 10 e 3 |

## Componentes por disciplina

| Pasta | Disciplina | Componente |
|---|---|---|
| [`visao/`](visao/) | Applied Computer Vision | Detector YOLO em tempo real + API `/detectar` e `/videos` + página web; envia as detecções ao MVP do grupo (`POST /api/ocorrencias`, origem `visao`) |

### Applied Computer Vision: entregáveis

- **Relatório em PDF (ABNT):** [`visao/docs/Relatorio_Visao_Computacional_Calcada_Livre.pdf`](visao/docs/Relatorio_Visao_Computacional_Calcada_Livre.pdf)
- **Código, documentação e como rodar:** [`visao/README.md`](visao/README.md)
- **Notebook com as saídas:** [`visao/notebooks/visao_calcada_livre.ipynb`](visao/notebooks/visao_calcada_livre.ipynb)
- **Vídeo de demonstração:** <https://www.youtube.com/watch?v=oh_gcKEkcOc>

Todos os componentes leem e gravam o mesmo objeto, a **ocorrência** (tipo, local, foto, prioridade,
status), cujo contrato está documentado em [`visao/README.md`](visao/README.md#api-contrato-da-ocorrência).
