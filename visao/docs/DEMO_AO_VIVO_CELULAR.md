# Gravando a demonstração (detecção ao vivo)

Roteiro técnico para gravar o vídeo da disciplina mostrando o detector funcionando em tempo real e a
ocorrência aparecendo no MVP. Há duas formas de capturar as imagens da calçada:

## Opção A — celular como câmera do computador (detecção ao vivo na tela)

1. No Android, instale o app **IP Webcam** (gratuito). No iPhone, use um app equivalente de "câmera IP".
2. Conecte o celular e o computador na **mesma rede Wi-Fi**.
3. No app, toque em **Iniciar servidor**; ele mostra um endereço como `http://192.168.0.15:8080`.
4. No computador, com a API rodando (`uvicorn api.main:app --port 8000`), execute:

   ```bash
   python scripts/05_video_demo.py --source http://192.168.0.15:8080/video --show --api http://127.0.0.1:8000 --lat -23.5614 --lon -46.6559 --out docs/demo_celular.mp4
   ```

5. Caminhe pela calçada apontando o celular para buracos, obstáculos e piso quebrado. A janela mostra as
   detecções em tempo real e cada barreira nova aparece no mapa do MVP (<http://127.0.0.1:8000>).
   Tecla **Q** encerra.

## Opção B — filmar primeiro e processar depois

1. Filme 30–60 s andando na calçada (celular na horizontal, na altura do peito).
2. Copie o arquivo para o computador e rode:

   ```bash
   python scripts/05_video_demo.py --source meu_video.mp4 --out docs/demo_celular.mp4 --api http://127.0.0.1:8000
   ```

## Cuidados (LGPD)

* O script já borra rostos e placas automaticamente; mesmo assim, prefira horários com pouca gente.
* Não filme dentro de imóveis nem documentos.
