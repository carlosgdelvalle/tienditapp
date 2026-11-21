# Carlos’s decision queue

Keep the program’s decision queue in the coordinator checkout on Arquimedes. Carlos chooses whether to answer directly or invoke Astra in a manual conversation. The Telegram notifier sends the question ID and status. The workflow never polls Astra, spends its tokens automatically, or executes replies received through chat.

## Entries

There are currently no operational questions. To open an entry, add a level-three heading with a unique ID and revision. Use the exact independent-work line below. Replace NNN with three unused digits. **Keep the Spanish notifier fields and values as written**; they are parsed by `scripts/notify-carlos`. The free-text engineering brief can be in English.

```text
### Q-NNN · r1
Trabajo independiente: sí
Tema del aviso: presupuesto
Estado: abierta
Packages: M1, G2
Decision needed:
Verified facts and source:
Options and consequences:
Coordinator recommendation:
Work that can proceed:
Carlos’s answer and date:
Verifier and resumption evidence:
```

Supported topic values are `presupuesto`, `acceso`, `proveedor`, `piloto`, `dispositivo`, and `criterio`. The bot maps each to a predefined Spanish message.

The coordinator maintains one current entry per question. Update its status and answer in place. Increment the revision only for a material change that requires another notification. Keep credentials, private destinations, CLABEs, merchant information, and token-bearing links out of the queue. Keep live entries local to the coordinator checkout and out of public commits. For a Telegram failure or uncertain delivery, follow the [runbook](telegram.md). A reply in Telegram does not authorize execution.
