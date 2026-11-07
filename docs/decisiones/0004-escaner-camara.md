# 0004 · Agregamos escáner con cámara: códigos de barras y foto de productos

- **Estado:** vigente (reemplaza en parte a 0002, que descartaba la cámara y los códigos de barras)
- **Fecha:** 2026-11-07
- **Contexto:** Eduardo pidió integrar un escáner con cámara para productos y códigos de barras. La cámara del navegador solo funciona en HTTPS o localhost, `BarcodeDetector` existe en Chrome pero no en Safari de iPhone, y el reconocimiento por foto necesita OpenAI Vision (todavía sin key). No hay una base de códigos de barras reales del catálogo y no se deben inventar.
- **Decisión:** en "Cobrar con Pey" hay dos botones. "Escanear código" lee EAN/UPC/Code128 con `BarcodeDetector`; un código desconocido se enlaza una vez a un producto del catálogo (`POST /api/barcode/link`) y después se agrega solo (`POST /api/barcode/lookup`). Si no hay cámara o detector, se escribe el código. "Foto de productos" manda la imagen a `POST /api/cart/photo` (OpenAI Vision con salida estructurada, solo `productId` del catálogo); sin `OPENAI_API_KEY` responde 503 y no inventa nada.
- **Opciones descartadas:** librería JS de lectura de códigos (más peso y dependencias para el demo); precargar códigos de barras "reales" sin verificarlos (riesgo de cobrar un producto equivocado).
- **Consecuencias:** el demo en la laptop (localhost, Chrome) puede escanear. En el celular hace falta HTTPS (túnel o deploy). La foto depende de la key de OpenAI. Los precios siguen saliendo siempre de la base.
- **Cómo se verifica:** `python -m pytest -q app/tests` (pruebas de enlazar, buscar, código inválido y foto sin key → 503); prueba en Chrome con cámara.
