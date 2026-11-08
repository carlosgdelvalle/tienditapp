#!/usr/bin/env bash
# Verificación rápida de Abarpay v1. Uso:
#   ./scripts/check_v1.sh
#   ./scripts/check_v1.sh <saleId>
# No imprime credenciales. La consola usa OWNER_PIN (default 1234).
set -euo pipefail
BASE="${ABARPAY_URL:-http://127.0.0.1:8000}"
PIN="${OWNER_PIN:-1234}"
echo "== health =="
curl -fsS "$BASE/api/health"
echo
echo "== reporte de hoy =="
curl -fsS "$BASE/api/reports/today"
echo
echo "== consola =="
curl -fsS -H "X-Owner-Pin: $PIN" "$BASE/api/console/summary"
echo
echo "== webhooks recientes =="
curl -fsS -H "X-Owner-Pin: $PIN" "$BASE/api/console/webhooks?limit=5"
echo
if [ "${1:-}" != "" ]; then
  echo "== venta $1 =="
  curl -fsS "$BASE/api/sales/$1"
  echo
fi
