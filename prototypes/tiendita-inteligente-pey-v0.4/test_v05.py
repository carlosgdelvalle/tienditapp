"""GAP-004/006/009/010/012/017/018: verificaciones locales sin pagos ni APIs externas."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from test_v04 import demo_client
from test_pey_integracion import make_real, stock

def test_codigo_barras_asocia_producto_sin_inventar_precios(tmp_path,monkeypatch):
    c=demo_client(tmp_path,monkeypatch)
    v=c.post('/api/barcodes/lookup',json={'code':'7501234567893'})
    assert v.status_code==404
    assert c.post('/api/barcodes/link',json={'code':'7501234567893','product_id':'producto-inexistente','confirm_registration':True}).status_code==404
    r=c.post('/api/barcodes/link',json={'code':'7501234567893','product_id':'agua','confirm_registration':True})
    assert r.status_code==200,r.text
    assert r.json()['id']=='agua' and r.json()['price_cents']==1500
    assert c.post('/api/barcodes/link',json={'code':'7501234567893','product_id':'pan','confirm_registration':True}).status_code==409
    assert c.post('/api/barcodes/lookup',json={'code':'7501234567893'}).json()['id']=='agua'
    assert c.post('/api/barcodes/lookup',json={'code':'abc?xyz'}).status_code==422
    assert c.post('/api/barcodes/link',json={'code':'121212','product_id':'pan','confirm_registration':True}).status_code==422
    assert c.post('/api/barcodes/link',json={'code':'7501234567890','product_id':'pan','confirm_registration':True}).status_code==422
    assert c.post('/api/barcodes/link',json={'code':'INT-1234','product_id':'pan'}).status_code==422
    internal=c.post('/api/barcodes/link',json={'code':'INT-1234','product_id':'pan','confirm_registration':True})
    assert internal.status_code==200 and internal.json()['code_kind']=='INTERNO'

def test_corte_separa_pruebas_fiados_y_simulaciones(tmp_path,monkeypatch):
    c=demo_client(tmp_path,monkeypatch,True)
    sale=c.post('/api/sales',json={'employee':'Ana','items':[{'id':'agua','qty':1}]}).json()
    assert c.post(f"/api/sales/{sale['id']}/qr").status_code==200
    assert c.post(f"/api/sales/{sale['id']}/demo-confirm").status_code==200
    date=datetime.now(ZoneInfo('America/Mexico_City')).date().isoformat()
    r=c.get('/api/reports/daily-close',params={'date':date})
    assert r.status_code==200,r.text
    j=r.json()
    assert j['commercial_cents']==0
    assert j['simulated_count']==1
    assert j['simulated_cents']==1500
    assert j['test_cents']==0
    assert c.get('/api/reports/daily-close',params={'date':'2026-02-30'}).status_code==422

def test_asesor_lee_pero_no_modifica_datos(tmp_path,monkeypatch):
    c=demo_client(tmp_path,monkeypatch)
    before=c.get('/api/bootstrap').json()
    for question in ('¿Qué productos debo reponer?','¿Cuánto vendí hoy?','¿Cuánto me deben de fiado?','¿Qué ventas están pendientes?','Borra las ventas'):
        r=c.post('/api/assistant/ask',json={'question':question})
        assert r.status_code==200,r.text
        assert r.json()['source']
        assert r.json()['answer']
    after=c.get('/api/bootstrap').json()
    assert before['products']==after['products']
    assert before['sales']==after['sales']
    assert c.post('/api/assistant/ask',json={'question':'x'}).status_code==422

def test_empleado_no_puede_abrir_reportes_asesor_ni_asociar_codigo(tmp_path,monkeypatch):
    c,auth,mod=make_real(tmp_path,monkeypatch)
    assert c.get('/api/reports/daily-close').status_code==401
    assert c.post('/api/employee/login',json={'name':'Ana','pin':'123456'}).status_code==200
    assert c.get('/api/reports/daily-close').status_code==403
    assert c.post('/api/barcodes/lookup',json={'code':'7501234567893'}).status_code==404
    assert c.post('/api/assistant/ask',json={'question':'cuanto vendi hoy'}).status_code==403
    assert c.post('/api/barcodes/link',json={'code':'7501234567893','product_id':'agua','confirm_registration':True}).status_code==403
    assert c.get('/api/reports/daily-close',headers=auth).status_code==200

def test_pwa_sin_cache_de_api_y_audio_distingue_pago(tmp_path,monkeypatch):
    base=Path(__file__).parent/'static'
    sw=(base/'service-worker.js').read_text(encoding='utf8')
    owner=(base/'app.js').read_text(encoding='utf8')
    employee=(base/'empleado.js').read_text(encoding='utf8')
    assert "CORE.includes(url.pathname)" in sw
    assert "/api/" not in sw
    assert "ownerSoundEnabled" in owner and "PEY confirmado" in owner
    assert "DEMO_PAGADA" not in owner[owner.index("lastSoundNoticeId"):][-700:]  # smoke only
    assert "serviceWorker.register" in employee

def test_autorizacion_no_altera_pago_real_sin_pey(tmp_path,monkeypatch):
    c,auth,mod=make_real(tmp_path,monkeypatch)
    original=stock(c,auth,'agua')
    response=c.post('/api/sales',headers=auth,json={'employee':'Ana','items':[{'id':'agua','qty':1}]})
    assert response.status_code==200
    sale=response.json()
    assert c.post(f"/api/sales/{sale['id']}/qr",headers=auth).status_code==200
    assert c.get(f"/api/sales/{sale['id']}/status",headers=auth).json()['status']=='PENDIENTE'
    assert stock(c,auth,'agua')==original
