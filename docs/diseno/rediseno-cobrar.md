# Rediseño de “Cobrar” para uso real en tiendita

Estado: propuesta de UX. Implementado en la app release: barra fija con total y salto a cobro, escaneo/dictado primero, texto y código opcionales, cantidades por presets y billetes rápidos en efectivo. Pendiente: escáner continuo, hoja de pago dedicada, QR a pantalla completa, perfil persistente y modo mostrador.

## Contexto de uso

El empleado suele tener el teléfono en una mano y el producto, la bolsa o el cambio en la otra. En hora pico hay clientes esperando, ruido, prisa y a veces manos mojadas o grasosas. Algunos productos tienen código; otros son a granel (“medio kilo de tortillas”). El dueño o un familiar también puede usar el teléfono, pero el empleado no debería iniciar sesión en cada venta.

La pantalla “Cobrar” actual está pensada como un formulario: campo de texto arriba, buscador, catálogo largo, carrito y pago abajo. En un teléfono de 390 × 844 el total y el botón de cobro quedan fuera de la primera pantalla. Para agregar tres productos hay que hacer scroll, tocar campos pequeños y, si se usa el teclado, la mitad de la pantalla desaparece.

## Objetivo

Reducir una venta típica de tres productos a menos de 15 segundos, sin teclado, con una sola mano y con el teléfono apoyado cuando ambas manos estén ocupadas.

## Principios

1. **Escanear primero, teclado nunca por defecto.** El campo de texto y el buscador pasan a una hoja secundaria.
2. **Zona del pulgar.** Las acciones críticas viven en el 40% inferior; arriba solo estado y contexto.
3. **Un toque = un artículo.** Cada escaneo agrega una unidad; repetir el mismo código incrementa la cantidad.
4. **Carrito y pago siempre visibles.** Una barra fija muestra artículos y total; nunca hay que buscarlos haciendo scroll.
5. **Cantidades con botones grandes.** 250 g, 500 g, 1 kg, 2 kg, +100 g y −100 g; para piezas, +/−.
6. **Confirmación sensorial.** Sonido corto, vibración y fila “último artículo” con Deshacer; no diálogos por cada producto.
7. **Progressive disclosure.** Carrito, cobro, cliente y cantidad se abren en hojas; la pantalla principal no se llena.
8. **Recuperación visible.** Si la red o PEY fallan, la app muestra la referencia y una salida segura; no deja al empleado atrapado.
9. **Empleado por turno, no por venta.** El perfil se elige al empezar y se mantiene.

## Nueva pantalla “Cobrar”

    ┌─────────────────────────────┐
    │ Abarpay · Lupita   ● Online │  estado compacto
    │ ┌─────────────────────────┐ │
    │ │                         │ │
    │ │      cámara en vivo     │ │  escaneo continuo
    │ │      ┌───────────┐      │ │
    │ │      │  código   │      │ │
    │ │      └───────────┘      │ │
    │ └─────────────────────────┘ │
    │ + Coca-Cola 2 pza  Deshacer │  último artículo
    │                             │
    ├─────────────────────────────┤
    │ 🛒 3 artículos       $58.00 │  barra fija
    │ [  Escanear  ] [ Dictar ]   │  botones grandes
    │ [      Cobrar $58.00     ]  │  CTA fijo
    └─────────────────────────────┘

### Comportamiento

- La cámara escanea de forma continua; no abre y cierra una pantalla por producto.
- Al detectar un código: agrega una unidad, vibra, suena y muestra “Coca-Cola 2 pza · Deshacer”.
- Si el mismo código sigue en el marco, no duplica; si vuelve a aparecer después de salir, incrementa.
- El botón **Productos** abre una cuadrícula grande de favoritos y recientes; el buscador queda dentro de esa hoja.
- **Dictar** es un botón grande de mantener para hablar; al soltar muestra chips interpretados (“2 cocas”, “medio kilo de tortillas”) con Editar/Deshacer.
- **Carrito** se abre desde la barra fija: filas grandes, +/−, total fijo y “Seguir cobrando”.
- **Cobrar** abre la hoja de pago; nunca está debajo del catálogo.

## Productos a granel

Después de escanear o elegir “Tortillas (kg)”, se abre una hoja con:

    0.25 kg   0.5 kg   1 kg   2 kg
        −100 g       +100 g
              [ Listo ]

No se abre el teclado. La cantidad se muestra como “0.5 kg” y el total se actualiza al instante con el precio del servidor. Para piezas, los botones son “−1” y “+1” con cantidad central grande.

## Pago

La hoja de pago muestra el total en grande y tres tarjetas:

- **Efectivo:** botones de billetes rápidos calculados desde el total (exacto, siguiente $20, $50, $100, $200), cambio enorme y “Cobrar en efectivo”. Se puede abrir un teclado numérico solo si hace falta.
- **PEY/CoDi:** QR a pantalla completa, brillo al máximo, pantalla encendida, monto y estado grandes. La confirmación solo llega del servidor; éxito con vibración, sonido y “Nuevo cobro”.
- **Fiado:** clientes recientes en chips grandes; alta de cliente en una hoja; saldo después de la venta.

## Cuando ambas manos están ocupadas

Dos modos:

1. **Teléfono en mano + producto en la otra:** todo se resuelve con el pulgar en la barra inferior; escanear y dictar están a la misma altura.
2. **Teléfono apoyado en el mostrador:** modo continuo con cámara; activación por voz (“Abarpay, dos cocas”) o botón de volumen/escáner Bluetooth; el carrito y el CTA se ven sin tocar la pantalla.

El modo apoyado debe funcionar en vertical y horizontal, con la cámara a un lado y el carrito/pago al otro. El modo no necesita una pantalla nueva: es la misma pantalla con orientación y tamaños adaptativos.

## Errores y casos raros

- **Código desconocido:** hoja grande “No está en el catálogo” con Elegir producto / Agregar rápido / Ignorar; no bloquea la venta.
- **Producto repetido:** incrementa cantidad y muestra “2 pza”; no crea filas duplicadas.
- **Red o PEY incierto:** conserva la venta con su folio, muestra “Revisar” y una acción de reintento/consulta; no atrapa al usuario en una pantalla sin salida.
- **Escaneo accidental:** Deshacer grande durante 5 segundos.
- **Sin conexión:** catálogo y códigos se cachean; el efectivo puede registrarse en cola si se implementa; PEY nunca se marca pagado localmente.

## Microinteracciones

- Sonido corto y vibración al agregar o quitar.
- Voz sintetizada con el total y el método al confirmar; opción de silencio.
- Totales y cambios con tipografía grande; el color no es la única señal.
- Sin animaciones largas, sin long-press, sin swipe obligatorio, sin objetivos menores de 56 dp.
- Pantalla encendida durante cámara y QR.

## Notas técnicas para Android

- Sustituir Google Code Scanner (una lectura por pantalla) por un escáner continuo con CameraX + ML Kit o ZXing, con permiso de cámara y debounce por código.
- Usar Scaffold con bottomBar y ModalBottomSheet de Compose para carrito, cantidad y pago.
- Mantener catálogo y códigos en caché local; el servidor confirma precios solo al crear la venta.
- Añadir FLAG_KEEP_SCREEN_ON y brillo máximo en QR; restaurar al salir.
- Mantener la regla: PEY solo pasa a pagado con confirmación del servidor; efectivo se registra, no se “verifica” como banco.
- Para el modo apoyado, soportar orientación y un diseño de dos paneles; opcionalmente botón de volumen/HID para escanear.
- Resolver la recuperación incierta con un id de intento/idempotencia persistido antes del POST, para no repetir el caso “Cobro por revisar”.

## Prioridad

**P0 para la demo**
- Barra fija con total y CTA de cobro.
- Carrito en hoja, sin scroll largo.
- Escaneo continuo o, si no se puede, escaneo repetible sin volver al inicio.
- Cantidades por botones grandes (media kilo, piezas).
- Efectivo con billetes rápidos y cambio grande.
- QR a pantalla completa, brillo y pantalla encendida.
- Perfil de empleado persistente por turno.
- Deshacer y confirmación sensorial.

**P1**
- Dictado por voz integrado en la barra.
- Cuadrícula de favoritos/recientes y búsqueda en hoja.
- Recuperación de intentos inciertos con idempotencia.
- Caché local de catálogo/códigos.

**P2**
- Modo mostrador/landscape.
- Escáner Bluetooth o botón de volumen.
- Activación por voz sin tocar.
- Cola de efectivo sin conexión.

## Lo que no haría

- Más campos de configuración en la pantalla de cobro.
- Un formulario de texto como acción principal.
- Confirmaciones por cada artículo.
- Depender de scroll para llegar al total o al pago.
- Iconos pequeños o gestos que requieran precisión.
- Mostrar estados técnicos largos durante la venta.

## Métricas de éxito

- Tres productos escaneados y cobrados en menos de 15 segundos.
- Cero aperturas de teclado en el recorrido normal.
- Una sola mano para el 100% de las acciones en modo teléfono en mano.
- Menos de tres toques después del último escaneo para efectivo.
- Ningún estado de error sin salida o referencia.
