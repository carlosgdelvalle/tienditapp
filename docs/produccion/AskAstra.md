# Cola de decisiones de Carlos

Fuente de decisiones del programa en el checkout coordinador de Arquimedes. Sólo Carlos decide si responde directamente o invoca Astra en una conversación manual. El notificador de Telegram comunica un ID y estado. No hay sondeo de Astra, presupuesto automático ni ejecución de respuestas recibidas por chat.

## Registro

Actualmente sin preguntas operativas. Para abrir una entrada añadir un encabezado de nivel tres con ID único y revisión; debajo escribir la línea exacta de trabajo independiente. Ejemplo de **formato** (sustituir NNN por tres dígitos libres):

```text
### Q-NNN · r1
Trabajo independiente: sí
Tema del aviso: presupuesto
Estado: abierta
Paquetes: M1, G2
Decisión requerida:
Hechos comprobados y fuente:
Opciones y consecuencia:
Recomendación del coordinador:
Qué puede avanzar mientras tanto:
Respuesta de Carlos / fecha:
Verificador y evidencia de reanudación:
```

Temas previstos: `presupuesto`, `acceso`, `proveedor`, `piloto`, `dispositivo`, `criterio`. El bot transforma el valor en una frase predefinida.

El coordinador mantiene una entrada vigente por pregunta. Actualiza estado y respuesta en la misma entrada; incrementa la revisión sólo ante un cambio material que requiere otro aviso. No copies credenciales, destinos privados, CLABE, información de comerciantes ni enlaces con tokens. La cola activa se mantiene en el checkout de coordinación, fuera de commits públicos. Ante fallo de Telegram o entrega dudosa consulta [el runbook](telegram.md). Una respuesta en Telegram no es autorización ejecutable.
