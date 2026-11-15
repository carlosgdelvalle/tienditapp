"""Pruebas sin red de pagos reales: fuentes PEY sustituidas por objetos falsos."""
import pytest
from test_pey_integracion import make_real, signed, stock


def live_evaluator(tmp_path, monkeypatch):
    monkeypatch.setenv('TIENDITA_EVALUATOR_DEMO', '1')
    monkeypatch.setenv('TIENDITA_TEST_ONE_CENT', '1')
    return make_real(tmp_path, monkeypatch)


def make_sale(client, auth):
    response = client.post('/api/sales', headers=auth,
        json={'employee':'Ana','items':[{'id':'agua','qty':1}]})
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale['charged_cents'] == 1
    qr = client.post(f"/api/sales/{sale['id']}/qr", headers=auth)
    assert qr.status_code == 200, qr.text
    return sale, qr.json()


def test_consulta_pey_recupera_pago_sin_webhook_una_vez(tmp_path, monkeypatch):
    client, auth, mod = live_evaluator(tmp_path, monkeypatch)
    original = stock(client, auth, 'agua')
    sale, qr = make_sale(client, auth)
    txid = 'TXRECOVERY12345'
    mod.pey.qr_transactions = lambda q: {'items':[{'id':txid,'status':'PAID'}]}
    mod.pey.transaction = lambda tx: {
        'id':tx,'status':'PAID','amount':0.01,'currency':'MXN',
        'paymentMethod':'CODI','payableType':'API_CODI_QR',
        'payableId':qr['qr_id'],'metadata':{'externalMetadata':{'orderId':str(sale['id'])}}}
    response = client.get(f"/api/sales/{sale['id']}/status", headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'PAGADA_PRUEBA'
    assert response.json()['verified_source'] == 'PEY_AUTHENTICATED_QR_API'
    assert stock(client,auth,'agua') == original-1
    assert client.get(f"/api/sales/{sale['id']}/status",headers=auth).json()['status'] == 'PAGADA_PRUEBA'
    assert stock(client,auth,'agua') == original-1


def test_consulta_no_aprueba_cobro_de_otro_qr(tmp_path, monkeypatch):
    client, auth, mod = live_evaluator(tmp_path, monkeypatch)
    original=stock(client,auth,'agua')
    sale, qr=make_sale(client,auth)
    mod.pey.qr_transactions=lambda q: {'items':[{'id':'TXOTHER12345','status':'PAID'}]}
    mod.pey.transaction=lambda tx: {
        'id':tx,'status':'PAID','amount':0.01,'currency':'MXN',
        'paymentMethod':'CODI','payableType':'API_CODI_QR','payableId':'OTHER-QR'}
    response=client.get(f"/api/sales/{sale['id']}/status",headers=auth)
    assert response.json()['status']=='PENDIENTE'
    assert stock(client,auth,'agua')==original


def test_evaluador_no_puede_pedir_push_ni_abono(tmp_path, monkeypatch):
    client,auth,mod=live_evaluator(tmp_path,monkeypatch)
    sale=client.post('/api/sales',headers=auth,
        json={'employee':'Ana','items':[{'id':'agua','qty':1}]}).json()
    assert client.post(f"/api/sales/{sale['id']}/push",headers=auth,
        json={'phone':'5512345678'}).status_code==403
    cid=client.get('/api/bootstrap',headers=auth).json()['clients'][0]['id']
    assert client.post(f"/api/clients/{cid}/payment-requests",headers=auth,
        json={'amount_cents':100,'method':'QR'}).status_code==403


def test_live_evaluador_no_activa_sin_limite_un_centavo(tmp_path,monkeypatch):
    monkeypatch.setenv('TIENDITA_EVALUATOR_DEMO','1')
    monkeypatch.setenv('TIENDITA_TEST_ONE_CENT','0')
    # make_real fuerza modo LIVE, por lo que se espera fallo seguro.
    with pytest.raises(AssertionError):
        make_real(tmp_path,monkeypatch)


def test_pin_invalidos_limitados(tmp_path,monkeypatch):
    client,auth,mod=live_evaluator(tmp_path,monkeypatch)
    for i in range(5):
        assert client.post('/api/employee/login',
            json={'name':'Ana','pin':'incorrecto'}).status_code==401
    assert client.post('/api/employee/login',
        json={'name':'Ana','pin':'123456'}).status_code==429
