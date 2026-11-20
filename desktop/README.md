# Módulo Desktop (Fase 10)

A interface web do J.A.R.V.I.S. está a ser desenvolvida em React + TypeScript + Vite sobre comunicação local REST/WebSocket com o backend FastAPI, permitindo empacotamento futuro sem reescrever a interface.

## Estratégia Recomendada

- **Tauri** (preferencial pelo baixo consumo de RAM e binário reduzido no Ubuntu Linux).
- **Electron** (alternativa caso surja necessidade específica de APIs Chromium).

Na Fase 10 serão adicionados aqui os ficheiros de configuração do wrapper desktop, integração com notificações nativas (`notify-send` / D-Bus) e serviço opcional de arranque automático (`systemd --user` ou `.desktop` autostart).
