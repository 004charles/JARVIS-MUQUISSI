# Arquitetura do J.A.R.V.I.S.

## Visão Geral

O J.A.R.V.I.S. segue uma arquitetura modular em camadas com separação estrita entre interface, comunicação em tempo real, núcleo de orquestração, inteligência artificial, memória, ferramentas e segurança.

```text
Frontend (React + TS + Vite + Tailwind + Framer Motion)
   │  REST (HTTP JSON) + WebSocket (/ws)
   ▼
Backend API (FastAPI + Pydantic)
   ├── Core (Config, Logging, EventBus)
   ├── Security (Permission Levels 1-3, Audit Trail) [Fase 4+]
   ├── AI Engine (Provider Interface: Ollama, OpenAI, Anthropic, Groq) [Fase 3+]
   ├── Agents (Core, Coding, System, Research, Automation, Project) [Fase 9+]
   ├── Tools (Files, Apps, System, Git, Web, Productivity) [Fase 4+]
   ├── Memory (Short-term, Long-term, Project, Operational) [Fase 7+]
   ├── System Monitor (psutil telemetry & alerts) [Fase 1 base / Fase 5 completo]
   ├── Voice (STT Whisper / TTS Piper) [Fase 6+]
   └── Database (SQLAlchemy + Alembic + SQLite)
```

## Princípios Arquiteturais

1. **Segurança por omissão**: Nenhuma resposta arbitrária da IA executa comandos no sistema. Toda ação passa por ferramentas tipadas, validação de parâmetros e verificação de nível de permissão (Nível 1 Seguro, Nível 2 Confirmação, Nível 3 Bloqueado/Especial).
2. **Baixo consumo de recursos**: SQLite local, backend assíncrono leve, frontend React otimizado, preparando empacotamento leve futuro com Tauri.
3. **Independência de fornecedor de IA**: Interface comum para modelos locais (Ollama) e APIs externas.
4. **Comunicação orientada a eventos**: O `EventBus` interno emite eventos estruturados (`assistant.listening`, `assistant.processing`, `assistant.speaking`, `tool.started`, `system.updated`, etc.) encaminhados via WebSocket para o frontend.
