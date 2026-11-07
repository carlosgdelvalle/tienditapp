"""GAP-004 / GAP-012: consultas de solo lectura; sin IA de pago ni mutaciones."""
import json
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Mexico_City")
PAID = ("PAGADA", "PAGADA_PRUEBA", "DEMO_PAGADA", "FIADA")


def daily_close(connection, day=None):
    local_day = day or datetime.now(ZONE).date().isoformat()
    try:
        begin = datetime.fromisoformat(local_day + "T00:00:00").replace(tzinfo=ZONE)
        end = datetime.fromisoformat(local_day + "T23:59:59.999999").replace(tzinfo=ZONE)
    except ValueError as exc:
        raise ValueError("Fecha inválida; usa AAAA-MM-DD") from exc
    if begin.date().isoformat() != local_day:
        raise ValueError("Fecha inválida")
    start_utc = begin.astimezone(timezone.utc).isoformat(timespec="seconds")
    end_utc = end.astimezone(timezone.utc).isoformat(timespec="seconds")
    rows = connection.execute(
        """SELECT id, employee, status, amount_cents, charged_cents,
                  created_at, paid_at, qr_mode, verified_source, items_json
           FROM sales
           WHERE (created_at>=? AND created_at<=?)
              OR (paid_at>=? AND paid_at<=?)
           ORDER BY id""",
        (start_utc, end_utc, start_utc, end_utc),
    ).fetchall()
    report = {"date":local_day, "timezone":"America/Mexico_City", "commercial_cents":0,
              "test_cents":0, "simulated_cents":0, "credit_cents":0,
              "pending_count":0, "uncertain_count":0, "paid_count":0,
              "test_count":0, "simulated_count":0, "credit_count":0,
              "employees":{}, "exceptions":[]}
    for row in rows:
        item = dict(row)
        status = item["status"]
        created_today = start_utc <= item["created_at"] <= end_utc
        paid_today = bool(item["paid_at"] and start_utc <= item["paid_at"] <= end_utc)
        if created_today and status == "PENDIENTE":
            report["pending_count"] += 1
            if (item["qr_mode"] or "").startswith("REAL_REVISAR"):
                report["uncertain_count"] += 1
                report["exceptions"].append({"id":item["id"],"reason":"Revisar respuesta PEY"})
        if created_today and status not in (*PAID, "PENDIENTE", "CANCELADA"):
            report["uncertain_count"] += 1
            report["exceptions"].append({"id":item["id"],"reason":status})
        if status == "FIADA" and created_today:
            report["credit_cents"] += item["amount_cents"]
            report["credit_count"] += 1
        if not paid_today:
            continue
        group = report["employees"].setdefault(item["employee"], {"commercial_cents":0,"sales":0})
        if status == "PAGADA":
            report["commercial_cents"] += item["charged_cents"]
            report["paid_count"] += 1
            group["commercial_cents"] += item["charged_cents"]
            group["sales"] += 1
        elif status == "PAGADA_PRUEBA":
            report["test_cents"] += item["charged_cents"]
            report["test_count"] += 1
        elif status == "DEMO_PAGADA":
            report["simulated_cents"] += item["amount_cents"]
            report["simulated_count"] += 1
    report["employees"] = [{"name":name, **metrics} for name,metrics in sorted(report["employees"].items())]
    report["exceptions"] = report["exceptions"][:30]
    report["note"] = "Pruebas, simulaciones y fiados NO son ingresos comerciales cobrados. No es conciliación bancaria ni cierre fiscal."
    return report


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c)!="Mn")


def answer_local(connection, question):
    """Intérprete controlado: jamás produce SQL dinámico ni modifica el registro."""
    q = normalize(question).strip()
    day = daily_close(connection)
    if any(word in q for word in ("vendi hoy", "vendido hoy", "ventas hoy", "cobre hoy", "cobrado hoy", "ingresos hoy")):
        return {"answer":f"Hoy se cobraron ${day['commercial_cents']/100:,.2f} MXN en {day['paid_count']} ventas comerciales. Los pagos de prueba y las simulaciones están separados.", "source":"corte local"}
    if "prueba" in q or "simulad" in q:
        return {"answer":f"Hoy: PEY de prueba ${day['test_cents']/100:,.2f} MXN; simulaciones ${day['simulated_cents']/100:,.2f} MXN. No son ingresos comerciales.", "source":"corte local"}
    if any(word in q for word in ("reponer", "agot", "stock", "inventario", "faltan productos", "existencias")):
        products=connection.execute("SELECT name, qty, min_qty, sales_day, lead_days FROM products WHERE qty<=min_qty ORDER BY qty ASC").fetchall()
        if not products:return {"answer":"No hay productos por debajo del mínimo registrado.", "source":"inventario local"}
        names=[f"{p['name']}: quedan {p['qty']} (mínimo {p['min_qty']})" for p in products[:8]]
        return {"answer":"Revisa para reponer: "+"; ".join(names)+".", "source":"inventario local"}
    if "fiado" in q or "deben" in q or "deuda" in q:
        balance=connection.execute("SELECT COALESCE(SUM(amount_cents),0) FROM credit_movements").fetchone()[0]
        return {"answer":f"Saldo pendiente registrado en fiados: ${balance/100:,.2f} MXN. No es ingreso cobrado.", "source":"libro local de fiados"}
    if "pendiente" in q or "conciliar" in q:
        return {"answer":f"Hoy hay {day['pending_count']} ventas pendientes y {day['uncertain_count']} casos que requieren revisión. No se consideran pagados.", "source":"corte local"}
    return {"answer":"Puedo consultar: ¿Cuánto vendí hoy?, ¿Qué productos debo reponer?, ¿Cuánto me deben de fiado?, ¿Qué ventas están pendientes? y ¿Cuánto fue de prueba? No modifico ventas ni inventario.", "source":"ayuda local"}
