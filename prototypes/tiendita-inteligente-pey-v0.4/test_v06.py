"""QA-012-001 / QA-010-001 / QA-017-001 / GAP-022 / GAP-024.
No external API calls, real payments, or hosted deployments.
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from test_v04 import demo_client
from test_pey_integracion import make_real


def test_codigo_existente_legacy_no_se_pierde(tmp_path, monkeypatch):
    c=demo_client(tmp_path,monkeypatch)
    # Migration-safe legacy links are still readable, but new unverified links are not allowed.
    from app import db
    # Test against the isolated TestClient database through the endpoint-created link.
    assert c.post('/api/barcodes/link',json={
        'code':'INT-9999','product_id':'agua','confirm_registration':True}).status_code==200
    assert c.post('/api/barcodes/lookup',json={'code':'INT-9999'}).json()['id']=='agua'
    assert c.post('/api/barcodes/link',json={
        'code':'111222','product_id':'leche','confirm_registration':True}).status_code==422


def test_reporte_proveedor_sin_datos_externos_ni_mutaciones(tmp_path,monkeypatch):
    c=demo_client(tmp_path,monkeypatch)
    before=c.get('/api/bootstrap').json()
    r=c.get('/api/analytics/supplier-demand')
    assert r.status_code==200,r.text
    j=r.json()
    assert j['scope']=='UNA_SUCURSAL'
    assert j['products'] and j['categories']
    assert all(p['suggested_units']>=0 and p['open_order_qty']>=0 for p in j['products'])
    assert c.get('/api/bootstrap').json()['products']==before['products']
    assert c.get('/api/bootstrap').json()['purchases']==before['purchases']


def test_tendencia_no_presenta_supuestos_como_ventas_observadas(tmp_path,monkeypatch):
    c=demo_client(tmp_path,monkeypatch)
    j=c.get('/api/analytics/demand-trends').json()
    assert j['historical_sufficient'] is False
    assert j['activity_days']==0
    assert all(r['basis']=='SUPUESTO_CATALOGO' and r['units_14d']==0 for r in j['rows'])
    assert 'Historial insuficiente' in j['note']
    # A DEMO sale on a single day is not sufficient to claim a validated trend.
    sale=c.post('/api/sales',json={'employee':'Ana','items':[{'id':'agua','qty':2}]}).json()
    assert c.post(f"/api/sales/{sale['id']}/qr").status_code==200
    assert c.post(f"/api/sales/{sale['id']}/demo-confirm").status_code==200
    x=c.get('/api/analytics/demand-trends').json()
    assert x['historical_sufficient'] is False
    agua=next(p for p in x['rows'] if p['id']=='agua')
    assert agua['units_14d']==2 and agua['basis']=='SUPUESTO_CATALOGO'


def test_analitica_restringida_al_dueno_con_pey_simulado(tmp_path,monkeypatch):
    c,auth,mod=make_real(tmp_path,monkeypatch)
    assert c.get('/api/analytics/supplier-demand').status_code==401
    assert c.get('/api/analytics/demand-trends').status_code==401
    assert c.post('/api/employee/login',json={'name':'Ana','pin':'123456'}).status_code==200
    assert c.get('/api/analytics/supplier-demand').status_code==403
    assert c.get('/api/analytics/demand-trends').status_code==403
    assert c.get('/api/analytics/supplier-demand',headers=auth).status_code==200
    assert c.get('/api/analytics/demand-trends',headers=auth).status_code==200


def test_qa_interfaz_no_borra_pregunta_y_pwa_identidad(tmp_path,monkeypatch):
    base=Path(__file__).parent/'static'
    js=(base/'app.js').read_text(encoding='utf8')
    assert "const editing=active&&['INPUT','TEXTAREA','SELECT'].includes(active.tagName)" in js
    assert 'if(!editing)render()' in js
    assert 'confirm_registration:true' in js
    assert 'load-supplier' in js and 'load-demand' in js
    for file in ('manifest.webmanifest','empleado.webmanifest'):
        data=json.loads((base/file).read_text(encoding='utf8'))
        assert data['name'].startswith('Abarpay')
        assert data['icons'][0]['src']=='/static/abarpay-icon.svg'
    icon=(base/'abarpay-icon.svg').read_text(encoding='utf8')
    assert '#29005C' in icon and '#CAFF38' in icon
    sw=(base/'service-worker.js').read_text(encoding='utf8')
    assert '/static/abarpay-icon.svg' in sw

