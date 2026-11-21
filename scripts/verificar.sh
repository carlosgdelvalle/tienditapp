#!/usr/bin/env bash
# Corre lo mismo que la CI: escaneo de secretos y pruebas (servidor + app).
# Uso: ./scripts/verificar.sh   (con el entorno de Python de app/requirements.txt activado)
set -uo pipefail
cd "$(dirname "$0")/.."
fallas=0

echo "== Secretos =="
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --source=. --redact --exit-code 1 || fallas=1
else
  if git ls-files -z | xargs -0 grep -nIE "whsec_[A-Za-z0-9+/=]{20,}|sk_live_[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9_-]{20,}" 2>/dev/null; then
    echo "Posible credencial en archivos versionados."; fallas=1
  else
    echo "Sin hallazgos (patrones mínimos; instala gitleaks para el escaneo completo)."
  fi
fi

echo "== Pruebas =="
python -m pytest -q server/tests || fallas=1
python -m pytest -q app/tests || fallas=1

if [ "$fallas" -ne 0 ]; then echo "VERIFICAR: FALLÓ"; exit 1; fi
echo "VERIFICAR: OK"
