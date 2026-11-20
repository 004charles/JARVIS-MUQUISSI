#!/usr/bin/env bash
set -euo pipefail

echo "=== J.A.R.V.I.S. — Verificação de Ambiente ==="
echo "OS: $(lsb_release -ds 2>/dev/null || uname -a)"
echo "Python: $(python3 --version 2>/dev/null || echo 'não encontrado')"
echo "Node.js: $(node --version 2>/dev/null || echo 'não encontrado')"
echo "npm: $(npm --version 2>/dev/null || echo 'não encontrado')"
echo "Git: $(git --version 2>/dev/null || echo 'não encontrado')"
echo "Ollama: $(ollama --version 2>/dev/null || echo 'não encontrado')"
echo "Memória livre:"
free -h | sed -n '1,2p'
echo "Espaço em disco:"
df -h . | sed -n '1,2p'
