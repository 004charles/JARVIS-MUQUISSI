# J.A.R.V.I.S. — Just A Rather Very Intelligent System

Assistente pessoal inteligente modular para Ubuntu Linux, construído com **Python (FastAPI)** no backend e **React + TypeScript + Vite + Tailwind CSS** no frontend.

## Estado Atual: Fase 1 — Fundação

- Estrutura modular completa (`backend/`, `frontend/`, `desktop/`, `docs/`, `scripts/`).
- Backend FastAPI com configuração por variáveis de ambiente (`pydantic-settings`), logging estruturado com rotação, SQLAlchemy + Alembic (SQLite), REST API e WebSocket em tempo real (`/ws`).
- Frontend React + TypeScript + Vite + Tailwind CSS com tema futurista escuro inicial e ligação em tempo real (REST + WebSocket) ao backend.
- Suite de testes automatizados (`pytest` no backend e build/typecheck no frontend).

## Requisitos de Sistema (Validados)

- Ubuntu Linux (x86_64)
- Python 3.12+ (ambiente atual: Python 3.14.4)
- Node.js 20+ e npm (ambiente atual: Node v24.21.0, npm 11.19.0)
- Ollama (opcional, instalado localmente para modelos locais na Fase 3)

## Arranque Rápido

### 1. Configurar ambiente
```bash
cp .env.example .env
```

### 2. Backend
```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

### 3. Frontend
```bash
cd frontend
npm run dev
```

### 4. Script auxiliar
```bash
./scripts/check_env.sh
```

## Documentação

- [Arquitetura do Sistema](docs/architecture.md)
- [Plano de Fases](docs/roadmap.md)
- [Preparação Desktop (Tauri / Electron)](desktop/README.md)
# JARVIS-MUQUISSI
# JARVIS-MUQUISSI
