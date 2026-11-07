"""Tiendita Inteligente — MVP Hackathon.

Servidor local para demostración. PEY LIVE solo si PEY_ENABLE_LIVE=1 y se configuran
PEY_API_KEY y PEY_WEBHOOK_SECRET en el entorno del servidor. Nunca en el navegador.
NO APTO PARA PRODUCCIÓN: falta autenticación fuerte, despliegue TLS, monitoreo, pruebas E2E.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import io
import json
import os
import secrets
from decimal import Decimal, InvalidOperation
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta, datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any
from pey_gateway import PeyClient, PeyError, verify_standard_webhook, money_to_cents
from cart_intelligence import parse_cart

import qrcode
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = os.environ.get('TIENDITA_DB', str(ROOT / 'tiendita.db'))
LIVE_REQUESTED = os.getenv('PEY_ENABLE_LIVE', '') == '1'
PEY_API_KEY = os.getenv('PEY_API_KEY', '')
PEY_WEBHOOK_SECRET = os.getenv('PEY_WEBHOOK_SECRET', '')
OPERATOR_TOKEN = os.getenv('TIENDITA_OPERATOR_TOKEN', '')
PEY_BANK_ACCOUNT_ID = os.getenv('PEY_BANK_ACCOUNT_ID', '')
TEST_ONE_CENT = os.getenv('TIENDITA_TEST_ONE_CENT','0') == '1'
EMPLOYEE_SESSION_SECRET = os.getenv('TIENDITA_SESSION_SECRET','')
# Bloqueo adicional: integracion real nunca se activa con solo copiar una llave.
LIVE = bool(LIVE_REQUESTED and PEY_API_KEY and PEY_WEBHOOK_SECRET and
            len(OPERATOR_TOKEN) >= 20 and
            os.getenv('PEY_CONFIRM_REAL_MONEY') == 'YES_I_AUTHORIZE' and
            os.getenv('TIENDITA_PUBLIC_URL', '').startswith('https://') and
            (os.getenv('TIENDITA_EVALUATOR_DEMO') != '1' or TEST_ONE_CENT) and
            len(EMPLOYEE_SESSION_SECRET)>=32 and
            all(os.getenv('TIENDITA_EMPLOYEE_PIN_'+n,'') for n in ('ANA','LUIS','MARIA')))
CONFIG_BLOCKED = LIVE_REQUESTED and not LIVE
pey = PeyClient(api_key=PEY_API_KEY) if LIVE else None

PORTAL_TITLE='Tiendita Inteligente'
conn_guard = threading.RLock()
app = FastAPI(title=PORTAL_TITLE, version='0.4.0')

def _employee_session(request: Request):
    if not EMPLOYEE_SESSION_SECRET: return None
    cookie=request.cookies.get('tiendita_employee','')
    try:
        value,mac=cookie.rsplit('.',1)
        expected=hmac.new(EMPLOYEE_SESSION_SECRET.encode(),value.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac,expected):return None
        employee,expiration=value.split('|')
        if employee not in ('Ana','Luis','María') or int(expiration)<time.time():return None
        return employee
    except (ValueError,TypeError,OverflowError):return None

@app.middleware('http')
async def require_operator(request:Request, call_next):
    # DEMO: interfaz libre, no colocar datos reales de clientes.
    # LIVE: token del dueño O sesión identificada del empleado, con rutas limitadas.
    if LIVE and request.url.path.startswith('/api/') and request.url.path not in ('/api/health','/api/employee/login'):
        operator=hmac.compare_digest(request.headers.get('x-tiendita-operator-key',''),OPERATOR_TOKEN)
        employee=_employee_session(request)
        if not operator and not employee:
            return JSONResponse(status_code=401,content={'detail':'Inicia sesión como empleado o dueño'})
        if employee and not operator:
            path=request.url.path
            allowed=(path in ('/api/employee/bootstrap','/api/cart/parse','/api/employee/logout') or
                     path=='/api/sales' and request.method=='POST' or
                     path.startswith('/api/sales/') and
                     (path.endswith('/qr') or path.endswith('/push') or path.endswith('/status')))
            if not allowed:return JSONResponse(status_code=403,content={'detail':'Acceso reservado al dueño'})
            if path.startswith('/api/sales/'):
                parts=path.split('/')
                if len(parts)>3:
                    try:sale_id=int(parts[3])
                    except ValueError:return JSONResponse(status_code=404,content={'detail':'Venta no encontrada'})
                    with db() as c:row=c.execute('SELECT employee FROM sales WHERE id=?',(sale_id,)).fetchone()
                    if not row or row['employee']!=employee:
                        return JSONResponse(status_code=403,content={'detail':'Venta de otro empleado'})
    return await call_next(request)

app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
# Recursos oficiales Abarpay reutilizados desde la raíz del repositorio.
BRANDING_DIR = ROOT.parents[1] / 'assets' / 'branding'
app.mount('/branding', StaticFiles(directory=BRANDING_DIR), name='branding')


def db():
    c = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=20000')
    return c


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def create_database():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with conn_guard:
        with db() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS products (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER NOT NULL,
              qty INTEGER NOT NULL, min_qty INTEGER NOT NULL,
              sales_day REAL NOT NULL, lead_days INTEGER NOT NULL, category TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lots (
              id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
              qty INTEGER NOT NULL, expiry TEXT, received_at TEXT NOT NULL,
              FOREIGN KEY(product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS purchases (
              id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
              qty_requested INTEGER NOT NULL, qty_received INTEGER NOT NULL DEFAULT 0,
              supplier TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              FOREIGN KEY(product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS sales (
              id INTEGER PRIMARY KEY AUTOINCREMENT, employee TEXT NOT NULL,
              items_json TEXT NOT NULL, amount_cents INTEGER NOT NULL,
              charged_cents INTEGER, expires_at TEXT, verified_source TEXT,
              status TEXT NOT NULL, qr_mode TEXT, qr_id TEXT,
              num_ref TEXT, transaction_id TEXT UNIQUE, receipt_token TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL, paid_at TEXT, pey_request_txid TEXT
            );
            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL,
              message TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS movements (
              id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
              delta INTEGER NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS webhook_events (
              webhook_id TEXT PRIMARY KEY, received_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clients (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              phone TEXT NOT NULL DEFAULT '',
              credit_limit_cents INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS credit_movements (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              client_id INTEGER NOT NULL,
              sale_id INTEGER,
              kind TEXT NOT NULL,
              amount_cents INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(client_id) REFERENCES clients(id),
              FOREIGN KEY(sale_id) REFERENCES sales(id)
            );
            CREATE TABLE IF NOT EXISTS payment_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              client_id INTEGER NOT NULL,
              amount_cents INTEGER NOT NULL,
              status TEXT NOT NULL,
              token TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              confirmed_at TEXT, pey_method TEXT, pey_qr_id TEXT,
              pey_transaction_id TEXT, pey_codi_id TEXT, pey_qr_string TEXT,
              FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            ''')
            # Migraciones no destructivas para bases de demostracion existentes
            for tab,cols in {'sales':{'pey_request_txid':'TEXT','charged_cents':'INTEGER','expires_at':'TEXT','verified_source':'TEXT'},
                             'payment_requests':{'pey_method':'TEXT','pey_qr_id':'TEXT',
                              'pey_transaction_id':'TEXT','pey_codi_id':'TEXT','pey_qr_string':'TEXT'}}.items():
                existing={r[1] for r in c.execute(f'PRAGMA table_info({tab})')}
                for col,typ in cols.items():
                    if col not in existing:c.execute(f'ALTER TABLE {tab} ADD COLUMN {col} {typ}')
            c.execute('UPDATE sales SET charged_cents=amount_cents WHERE charged_cents IS NULL')
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_requesttx ON sales(pey_request_txid)')
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_pr_qr ON payment_requests(pey_qr_id)')
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_pr_tx ON payment_requests(pey_transaction_id)')
            if c.execute('SELECT COUNT(*) FROM clients').fetchone()[0] == 0:
                c.execute('INSERT INTO clients(name,phone,credit_limit_cents,created_at) VALUES(?,?,?,?)',
                          ('Doña Lupita (ejemplo)','',100000,now()))
            if c.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
                seed=[
                  ('leche','Leche 1 L',2800,7,10,4.0,2,'Lácteos',4),
                  ('pan','Pan de caja',4500,6,8,2.0,2,'Panadería',5),
                  ('huevo','Huevo (docena)',4800,17,8,1.5,2,'Básicos',12),
                  ('agua','Agua 600 ml',1500,26,15,6.0,2,'Bebidas',None),
                  ('refresco','Refresco 600 ml',1900,9,12,4.0,2,'Bebidas',None),
                  ('arroz','Arroz 1 kg',3000,14,8,1.3,3,'Abarrotes',None),
                  ('cafe','Café molido 250 g',8500,5,8,1.2,3,'Abarrotes',None),
                  ('yogur','Yogur natural',2200,8,10,3.0,2,'Lácteos',3),
                ]
                for id,name,price,qty,minimum,day,lead,cat,expiry in seed:
                    c.execute('INSERT INTO products VALUES (?,?,?,?,?,?,?,?)',(id,name,price,qty,minimum,day,lead,cat))
                    dt=(date.today()+timedelta(days=expiry)).isoformat() if expiry else None
                    c.execute('INSERT INTO lots(product_id,qty,expiry,received_at) VALUES (?,?,?,?)',(id,qty,dt,now()))
                c.execute('INSERT INTO notifications(role,message,created_at) VALUES (?,?,?)',('dueno','Bienvenido. Tus empleados pueden registrar ventas y cobros desde su celular.',now()))

create_database()


def result_rows(cur):
    return [dict(row) for row in cur.fetchall()]


def reserved(c):
    vals={}
    rows=c.execute("SELECT items_json FROM sales WHERE status='PENDIENTE'").fetchall()
    for r in rows:
        for x in json.loads(r['items_json']):
            vals[x['id']]=vals.get(x['id'],0)+x['qty']
    return vals


def snapshot():
    with db() as c:
        hold=reserved(c)
        products=[]
        for p in result_rows(c.execute('SELECT * FROM products ORDER BY name')):
            p['available']=max(0,p['qty']-hold.get(p['id'],0))
            p['recommended']=max(0,round(p['min_qty']+p['sales_day']*p['lead_days']-p['qty']))
            lot=c.execute("SELECT MIN(expiry) AS expiry FROM lots WHERE product_id=? AND qty>0 AND expiry IS NOT NULL",(p['id'],)).fetchone()
            p['next_expiry']=lot['expiry'] if lot else None
            products.append(p)
        sales=result_rows(c.execute('SELECT id,employee,items_json,amount_cents,status,qr_mode,qr_id,created_at,paid_at,receipt_token FROM sales ORDER BY id DESC LIMIT 40'))
        for sale in sales: sale['items']=json.loads(sale.pop('items_json'))
        purchases=result_rows(c.execute('SELECT pu.*, pr.name AS product_name FROM purchases pu JOIN products pr ON pu.product_id=pr.id ORDER BY pu.id DESC LIMIT 40'))
        notifications=result_rows(c.execute('SELECT * FROM notifications ORDER BY id DESC LIMIT 40'))
        clients=result_rows(c.execute("""SELECT cl.*, COALESCE(SUM(cm.amount_cents),0) AS balance_cents
                FROM clients cl LEFT JOIN credit_movements cm ON cm.client_id=cl.id
                GROUP BY cl.id ORDER BY cl.name"""))
        payment_requests=result_rows(c.execute("""SELECT pr.*, cl.name AS client_name FROM payment_requests pr
                JOIN clients cl ON cl.id=pr.client_id ORDER BY pr.id DESC LIMIT 40"""))
        net=c.execute("SELECT COALESCE(SUM(charged_cents),0) FROM sales WHERE status='PAGADA'").fetchone()[0]
        count=c.execute("SELECT COUNT(*) FROM sales WHERE status='PAGADA'").fetchone()[0]
        return {'products':products,'sales':sales,'purchases':purchases,'notifications':notifications,'clients':clients,'payment_requests':payment_requests,
                'totals':{'sales_cents':net,'sales_count':count,'real_collected_cents':net,
                          'test_pey_receipts_cents':c.execute("SELECT COALESCE(SUM(charged_cents),0) FROM sales WHERE status='PAGADA_PRUEBA'").fetchone()[0],
                          'test_pey_count':c.execute("SELECT COUNT(*) FROM sales WHERE status='PAGADA_PRUEBA'").fetchone()[0],
                          'demo_sales_count':c.execute("SELECT COUNT(*) FROM sales WHERE status='DEMO_PAGADA'").fetchone()[0], 'low_stock':sum(p['qty']<=p['min_qty'] for p in products),'credit_outstanding_cents':sum(x['balance_cents'] for x in clients)},
                'config':{'pey_mode':'REAL' if LIVE else ('BLOQUEADO' if CONFIG_BLOCKED else 'DEMO'),
                          'server_time':now(), 'single_branch':'Sucursal Centro',
                          'needs_internet_for_pey':True,'one_cent_test':TEST_ONE_CENT,'ai_enabled':bool(os.getenv('OPENAI_API_KEY'))}}

@app.get('/empleado')
def employee_home(): return FileResponse(ROOT/'static'/'empleado.html')

@app.get('/')
def home(): return FileResponse(ROOT/'static'/'index.html')

@app.get('/manifest.webmanifest')
def manifest(): return FileResponse(ROOT/'static'/'manifest.webmanifest')

@app.get('/service-worker.js')
def sw(): return FileResponse(ROOT/'static'/'service-worker.js',media_type='application/javascript')

@app.get('/api/health')
def health(): return {'ok':True,'mode':'REAL' if LIVE else ('BLOQUEADO' if CONFIG_BLOCKED else 'DEMO')}

@app.get('/api/bootstrap')
def bootstrap(): return snapshot()

class EmployeeLoginIn(BaseModel):
    name: str
    pin: str = ''

@app.post('/api/employee/login')
def employee_login(value:EmployeeLoginIn):
    names={'Ana':'ANA','Luis':'LUIS','María':'MARIA'}
    if value.name not in names:raise HTTPException(400,'Empleado desconocido')
    if LIVE:
        pin=os.getenv('TIENDITA_EMPLOYEE_PIN_'+names[value.name],'')
        if not pin or not hmac.compare_digest(pin,value.pin):raise HTTPException(401,'PIN incorrecto')
    expires=int(time.time())+8*3600
    token=f'{value.name}|{expires}'
    signature=hmac.new(EMPLOYEE_SESSION_SECRET.encode(),token.encode(),hashlib.sha256).hexdigest() if EMPLOYEE_SESSION_SECRET else ''
    response=JSONResponse({'ok':True,'name':value.name,'demo':not LIVE})
    if EMPLOYEE_SESSION_SECRET:
        response.set_cookie('tiendita_employee',token+'.'+signature,httponly=True,secure=LIVE,samesite='strict',max_age=8*3600,path='/')
    return response

@app.post('/api/employee/logout')
def employee_logout():
    response=JSONResponse({'ok':True});response.delete_cookie('tiendita_employee',path='/');return response

@app.get('/api/employee/bootstrap')
def employee_bootstrap(request:Request):
    with db() as c:
        hold=reserved(c)
        products=[{'id':p['id'],'name':p['name'],'price_cents':p['price_cents'],
                   'available':max(0,p['qty']-hold.get(p['id'],0))} for p in result_rows(c.execute('SELECT * FROM products ORDER BY name'))]
        actor=_employee_session(request)
        notices=result_rows(c.execute("SELECT id,message FROM notifications WHERE role='empleado' ORDER BY id DESC LIMIT 12"))
        return {'products':products,'notifications':notices,'employee':actor,
                'config':{'pey_mode':'REAL' if LIVE else ('BLOQUEADO' if CONFIG_BLOCKED else 'DEMO'),
                          'one_cent_test':TEST_ONE_CENT,'ai_enabled':bool(os.getenv('OPENAI_API_KEY'))}}

class ParseCartIn(BaseModel):
    text:str=Field(min_length=1,max_length=500)

@app.post('/api/cart/parse')
def parse_cart_request(value:ParseCartIn,request:Request):
    if LIVE and not (_employee_session(request) or hmac.compare_digest(request.headers.get('x-tiendita-operator-key',''),OPERATOR_TOKEN)):
        raise HTTPException(401,'Autenticación requerida')
    catalog=employee_bootstrap(request)['products']
    try:return parse_cart(value.text,catalog)
    except ValueError as exc:raise HTTPException(422,str(exc))
    except Exception:raise HTTPException(503,'Interpretación IA no disponible; puedes registrar manualmente')



class PurchaseIn(BaseModel):
    product_id: str
    quantity: int = Field(ge=1,le=10000)
    supplier: str = Field(default='Proveedor local',max_length=90)

@app.post('/api/purchases')
def create_purchase(p:PurchaseIn):
    with conn_guard, db() as c:
        if not c.execute('SELECT id FROM products WHERE id=?',(p.product_id,)).fetchone(): raise HTTPException(404,'Producto no existe')
        cur=c.execute('INSERT INTO purchases(product_id,qty_requested,supplier,status,created_at) VALUES(?,?,?,?,?)',
                (p.product_id,p.quantity,p.supplier,'PENDIENTE',now()))
        c.execute('INSERT INTO notifications(role,message,created_at) VALUES(?,?,?)',('dueno',f'Pedido a proveedor #{cur.lastrowid}: {p.quantity} piezas solicitadas.',now()))
        return {'id':cur.lastrowid,'status':'PENDIENTE'}

class ReceiveIn(BaseModel):
    quantity: int = Field(ge=1,le=10000)
    expiry: str | None = None
    employee: str = 'Ana'

@app.post('/api/purchases/{pid}/receive')
def receive_purchase(pid:int,data:ReceiveIn):
    if data.expiry:
        try: date.fromisoformat(data.expiry)
        except ValueError: raise HTTPException(400,'Fecha de caducidad inválida')
    with conn_guard, db() as c:
        po=c.execute('SELECT * FROM purchases WHERE id=?',(pid,)).fetchone()
        if not po: raise HTTPException(404,'Pedido no existe')
        if po['status']=='RECIBIDO': raise HTTPException(409,'Este pedido ya fue recibido')
        c.execute('UPDATE products SET qty=qty+? WHERE id=?',(data.quantity,po['product_id']))
        c.execute('INSERT INTO lots(product_id,qty,expiry,received_at) VALUES(?,?,?,?)',(po['product_id'],data.quantity,data.expiry,now()))
        c.execute('UPDATE purchases SET qty_received=?, status=? WHERE id=?',(data.quantity,'RECIBIDO',pid))
        c.execute('INSERT INTO movements(product_id,delta,actor,reason,created_at) VALUES(?,?,?,?,?)',(po['product_id'],data.quantity,data.employee,f'Recepción de pedido #{pid}',now()))
        c.execute('INSERT INTO notifications(role,message,created_at) VALUES(?,?,?)',('dueno',f'{data.employee} recibió {data.quantity} piezas del pedido #{pid}.',now()))
    return {'ok':True,'id':pid,'status':'RECIBIDO'}

class SaleItem(BaseModel):
    id: str
    qty: int=Field(ge=1,le=1000)

class SaleIn(BaseModel):
    items: list[SaleItem]=Field(min_length=1,max_length=80)
    employee: str=Field(default='Ana',min_length=1,max_length=50)

@app.post('/api/sales')
def create_sale(s:SaleIn,request:Request):
    parsed={}
    for x in s.items: parsed[x.id]=parsed.get(x.id,0)+x.qty
    with conn_guard, db() as c:
        c.execute('BEGIN IMMEDIATE')
        hold=reserved(c)
        items=[]; total=0
        for id,qty in parsed.items():
            p=c.execute('SELECT * FROM products WHERE id=?',(id,)).fetchone()
            if not p: raise HTTPException(404,f'Producto {id} no existe')
            if qty>p['qty']-hold.get(id,0): raise HTTPException(409,f'Sin inventario suficiente: {p["name"]}')
            items.append({'id':id,'name':p['name'],'qty':qty,'price_cents':p['price_cents']})
            total+=p['price_cents']*qty
        charged=1 if TEST_ONE_CENT else total
        employee=_employee_session(request) or s.employee
        cur=c.execute('INSERT INTO sales(employee,items_json,amount_cents,charged_cents,expires_at,status,receipt_token,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (employee,json.dumps(items,ensure_ascii=False),total,charged,
                       (datetime.now(timezone.utc)+timedelta(seconds=600)).isoformat(),
                       'PENDIENTE',secrets.token_urlsafe(16),now()))
    return {'id':cur.lastrowid,'amount_cents':total,'charged_cents':charged,'status':'PENDIENTE',
            'one_cent_test':TEST_ONE_CENT}


def qr_png_data(payload):
    qr=qrcode.QRCode(border=2,box_size=8,error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload); qr.make(fit=True)
    b=io.BytesIO(); qr.make_image(fill_color='#162b31',back_color='#ffffff').save(b,format='PNG')
    return base64.b64encode(b.getvalue()).decode('ascii')

class PushIn(BaseModel):
    phone: str = Field(pattern=r'^[0-9]{10}$')


def payment_params(amount_cents:int, ref:int, concept:str, kind:str, **extras):
    if ref<1 or ref>9999999:raise HTTPException(400,'Referencia fuera del rango de 7 digitos CoDi')
    p={'amount':amount_cents/100,'concept':concept[:40], 'expiration':600,
       'numRef':str(ref), 'metadata':{'orderId':str(ref),'kind':kind}}
    if PEY_BANK_ACCOUNT_ID:p['bankAccountId']=PEY_BANK_ACCOUNT_ID
    return {**p, **extras}


def send_sale_pey(sid:int, kind:str, phone:str|None=None):
    if CONFIG_BLOCKED:raise HTTPException(503,'Modo PEY BLOQUEADO: configuracion segura incompleta')
    with conn_guard, db() as c:
        c.execute('BEGIN IMMEDIATE')
        s=c.execute('SELECT * FROM sales WHERE id=?',(sid,)).fetchone()
        if not s:raise HTTPException(404,'Venta no existe')
        if s['status']!='PENDIENTE' or s['qr_id']:
            raise HTTPException(409,'La venta ya no admite una nueva solicitud de pago')
        if LIVE:
            # Reserva el intento antes de llamar a PEY: ante timeout NO se reintenta
            # automaticamente una peticion potencialmente aceptada por el banco.
            c.execute('UPDATE sales SET qr_mode=?,qr_id=? WHERE id=?',('REAL_INICIANDO',f'INICIANDO-{sid}',sid))
        else:
            mode='DEMO_QR' if kind=='QR' else 'DEMO_PN'
            c.execute('UPDATE sales SET qr_mode=?,qr_id=?,num_ref=? WHERE id=?',(mode,f'DEMO-{sid}',str(sid),sid))
            if kind=='QR':
                return {'mode':'DEMO','method':'QR','qr_image':qr_png_data(f'https://demo.invalid/NO-PAGAR/venta-{sid}'),
                        'amount_cents':s['charged_cents'],'qr_id':f'DEMO-{sid}',
                        'label':'QR SIMULADO: no cobra dinero.'}
            return {'mode':'DEMO','method':'PUSH','amount_cents':s['charged_cents'],
                    'label':'PUSH SIMULADO: no se envio nada al celular.'}
    try:
        if kind=='QR':
            r=pey.create_qr(payment_params(s['charged_cents'],sid,f'Tiendita venta {sid}','sale'))
            qr_image=qr_png_data(r['qrString'])
        else:
            r=pey.create_push(payment_params(s['charged_cents'],sid,f'Tiendita venta {sid}','sale',phoneNumber=phone))
    except PeyError as exc:
        with conn_guard,db() as c:
            c.execute('UPDATE sales SET qr_mode=? WHERE id=?',('REAL_REVISAR',sid))
        raise HTTPException(502,f'PEY no confirmado ({exc.code}); revisar en portal antes de reintentar')
    with conn_guard,db() as c:
        if kind=='QR':
            c.execute('UPDATE sales SET qr_mode=?,qr_id=?,num_ref=? WHERE id=?',('REAL_QR',r['id'],str(sid),sid))
            return {'mode':'REAL','method':'QR','qr_id':r['id'],'qr_image':qr_image,
                    'amount_cents':s['charged_cents'],'label':'QR CoDi solicitado a PEY. Espera confirmacion firmada.'}
        c.execute('UPDATE sales SET qr_mode=?,qr_id=?,num_ref=?,pey_request_txid=? WHERE id=?',
                  ('REAL_PN',r['codiId'],str(sid),r['transactionId'],sid))
        return {'mode':'REAL','method':'PUSH','amount_cents':s['charged_cents'],
                'label':'PEY acepto la solicitud bancaria. Pago PENDIENTE hasta confirmacion.',
                'folio':r['codiId']}

@app.get('/api/sales/{sid}/status')
def sale_status(sid:int):
    with db() as c:
        sale=c.execute('SELECT id,employee,amount_cents,charged_cents,status,qr_mode,qr_id,transaction_id,verified_source,expires_at,paid_at FROM sales WHERE id=?',(sid,)).fetchone()
        if not sale:raise HTTPException(404,'Venta no encontrada')
        return dict(sale)

@app.post('/api/sales/{sid}/qr')
def generate_qr(sid:int):return send_sale_pey(sid,'QR')

@app.post('/api/sales/{sid}/push')
def generate_push(sid:int,item:PushIn):return send_sale_pey(sid,'PN',item.phone)

def consume_stock(c, sale_row, mode, transaction_id):
    if sale_row['status']!='PENDIENTE': raise ValueError('Venta ya procesada')
    for item in json.loads(sale_row['items_json']):
        c.execute('UPDATE products SET qty=qty-? WHERE id=? AND qty>=?',(item['qty'],item['id'],item['qty']))
        if c.execute('SELECT changes()').fetchone()[0]!=1: raise ValueError('Existencias insuficientes al confirmar')
        remaining=item['qty']
        lots=c.execute('SELECT id,qty FROM lots WHERE product_id=? AND qty>0 ORDER BY (expiry IS NULL),expiry,id',(item['id'],)).fetchall()
        for lot in lots:
            used=min(remaining,lot['qty'])
            c.execute('UPDATE lots SET qty=qty-? WHERE id=?',(used,lot['id']))
            remaining-=used
            if remaining==0:break
        c.execute('INSERT INTO movements(product_id,delta,actor,reason,created_at) VALUES (?,?,?,?,?)',
                  (item['id'],-item['qty'],sale_row['employee'],f'Venta #{sale_row["id"]} {mode}',now()))
    c.execute('UPDATE sales SET status=?,transaction_id=?,paid_at=?,verified_source=? WHERE id=?',
              (mode,transaction_id,None if mode=='FIADA' else now(),
               'PEY_SIGNED_WEBHOOK_AND_API' if mode in ('PAGADA','PAGADA_PRUEBA') else 'SIMULACION' if mode=='DEMO_PAGADA' else 'FIADO',sale_row['id']))
    suffix='(FIADO: aún no se pagó)' if mode=='FIADA' else ('(SIMULACIÓN: sin transferencia)' if mode=='DEMO_PAGADA' else ('(PEY PRUEBA REAL: no es venta comercial)' if mode=='PAGADA_PRUEBA' else '(PEY confirmado)'))
    c.execute('INSERT INTO notifications(role,message,created_at) VALUES (?,?,?)',
              ('dueno',f'Venta #{sale_row["id"]}: ${sale_row["amount_cents"]/100:,.2f} · {sale_row["employee"]} · {suffix}',now()))
    c.execute('INSERT INTO notifications(role,message,created_at) VALUES (?,?,?)',
              ('empleado',f'Venta #{sale_row["id"]}: {"Pago real confirmado" if mode=="PAGADA" else ("Fiado registrado (aún sin cobrar)" if mode=="FIADA" else "Pago de prueba simulado")}.',now()))

@app.post('/api/sales/{sid}/demo-confirm')
def demo_confirm(sid:int):
    if LIVE or CONFIG_BLOCKED: raise HTTPException(403,'Simulación deshabilitada en configuración PEY real o incompleta')
    with conn_guard, db() as c:
        c.execute('BEGIN IMMEDIATE')
        s=c.execute('SELECT * FROM sales WHERE id=?',(sid,)).fetchone()
        if not s: raise HTTPException(404,'Venta no existe')
        if s['qr_mode'] not in ('DEMO_QR','DEMO_PN'): raise HTTPException(409,'Solo es posible simular pago sobre QR DEMO')
        if s['status']!='PENDIENTE':raise HTTPException(409,'Venta ya procesada')
        try: consume_stock(c,s,'DEMO_PAGADA',f'DEMO-{sid}-{int(time.time())}')
        except ValueError as e: raise HTTPException(409,str(e))
    return {'ok':True,'status':'DEMO_PAGADA','message':'SIMULACIÓN. No hubo transferencia de dinero.'}

@app.post('/api/sales/{sid}/cancel')
def cancel_sale(sid:int):
    with conn_guard, db() as c:
        s=c.execute('SELECT * FROM sales WHERE id=?',(sid,)).fetchone()
        if not s:raise HTTPException(404,'Venta no existe')
        if s['status']!='PENDIENTE':raise HTTPException(409,'Venta ya no está pendiente')
        if (s['qr_mode'] or '').startswith('REAL_'): raise HTTPException(409,'No cancelar un cobro CoDi real sin reconciliar primero con PEY')
        c.execute('UPDATE sales SET status=? WHERE id=?',('CANCELADA',sid))
    return {'ok':True}


def check_standard_webhook(headers,raw:bytes):
    return verify_standard_webhook(headers,raw,PEY_WEBHOOK_SECRET)


def verify_pey_transaction(payload:dict):
    # Signed event by itself is insufficient: perform independent, authenticated read-back.
    if not LIVE or pey is None:raise HTTPException(503,'No hay conexión PEY real')
    txid=payload.get('transactionId')
    if not isinstance(txid,str) or not txid:raise HTTPException(400,'Transacción PEY faltante')
    try: detail=pey.transaction(txid)
    except PeyError:raise HTTPException(503,'No se pudo verificar transacción con PEY. Reintentar el webhook')
    expected_type={'codi.qr.payment_received':'API_CODI_QR','codi.pn.payment_received':'API_CODI_PN'}.get(payload.get('type'))
    try: verified_amount=money_to_cents(detail.get('amount'))
    except ValueError:raise HTTPException(409,'Monto PEY inválido')
    if (detail.get('status')!='PAID' or detail.get('currency')!='MXN' or
        detail.get('paymentMethod')!='CODI' or detail.get('payableType')!=expected_type or
        detail.get('id')!=txid or verified_amount!=money_to_cents(payload.get('amount'))):
        raise HTTPException(409,'Transacción bancaria no coincide con evento firmado')
    return detail

def reconcile_payment(payload:dict, webhook_id:str):
    event=payload.get('type')
    if event not in ('codi.qr.payment_received','codi.pn.payment_received'):
        return {'ok':True,'ignored':True}
    txid=payload.get('transactionId')
    amount=payload.get('amount')
    if not isinstance(txid,str) or not txid:
        raise HTTPException(400,'Identificador de transaccion ausente')
    try:amount_cents=money_to_cents(amount)
    except ValueError:raise HTTPException(400,'Monto invalido')
    meta=payload.get('metadata') or {}
    external=meta.get('externalMetadata') if isinstance(meta,dict) else {}
    external=external if isinstance(external,dict) else {}
    number=str(payload.get('numRef',''))
    with conn_guard,db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM webhook_events WHERE webhook_id=?',(webhook_id,)).fetchone():
            return {'ok':True,'duplicate':True}
        if event=='codi.qr.payment_received':
            qr=payload.get('codiQrId')
            sale=c.execute('SELECT * FROM sales WHERE qr_id=? AND qr_mode=?',(qr,'REAL_QR')).fetchone()
            pr=c.execute('SELECT * FROM payment_requests WHERE pey_qr_id=? AND pey_method=?',
                         (qr,'REAL_QR')).fetchone()
        else:
            sale=c.execute('SELECT * FROM sales WHERE pey_request_txid=? AND qr_mode=?',(txid,'REAL_PN')).fetchone()
            pr=c.execute('SELECT * FROM payment_requests WHERE pey_transaction_id=? AND pey_method=?',
                         (txid,'REAL_PN')).fetchone()
        if bool(sale)==bool(pr):raise HTTPException(409,'Pago sin solicitud unica identificable; conciliar manualmente')
        if sale:
            if amount_cents!=sale['charged_cents']:raise HTTPException(409,'Importe incorrecto')
            if number and number!=str(sale['id']):raise HTTPException(409,'Referencia CoDi incorrecta')
            if external.get('orderId') and str(external['orderId'])!=str(sale['id']):
                raise HTTPException(409,'Metadatos inconsistentes')
            if sale['status'] in ('PAGADA','PAGADA_PRUEBA'):
                if sale['transaction_id']!=txid:raise HTTPException(409,'Otro pago sobre venta conciliada')
                c.execute('INSERT INTO webhook_events VALUES(?,?)',(webhook_id,now()))
                return {'ok':True,'duplicate':True}
            if sale['status']!='PENDIENTE':raise HTTPException(409,'Venta no pendiente')
            try:consume_stock(c,sale,'PAGADA_PRUEBA' if TEST_ONE_CENT else 'PAGADA',txid)
            except (ValueError,sqlite3.IntegrityError):raise HTTPException(409,'Pago no conciliado; revisar inventario')
            c.execute('INSERT INTO notifications(role,message,created_at) VALUES(?,?,?)',
                      ('cliente',f'Pago de venta #{sale["id"]} recibido y verificado. Tu comprobante esta disponible.',now()))
            result={'ok':True,'type':'sale','status':'PAGADA_PRUEBA' if TEST_ONE_CENT else 'PAGADA','id':sale['id']}
        else:
            if amount_cents!=pr['amount_cents']:raise HTTPException(409,'Importe incorrecto')
            if number and number!=str(pr['id']):raise HTTPException(409,'Referencia de fiado incorrecta')
            if external.get('orderId') and str(external['orderId'])!=str(pr['id']):
                raise HTTPException(409,'Metadatos de fiado inconsistentes')
            if pr['status']=='PAGADA':
                if pr['pey_transaction_id']!=txid:raise HTTPException(409,'Solicitud ya cobrada con otra transaccion')
                c.execute('INSERT INTO webhook_events VALUES(?,?)',(webhook_id,now()))
                return {'ok':True,'duplicate':True}
            if pr['status']!='PENDIENTE':raise HTTPException(409,'Solicitud no pendiente')
            balance=c.execute('SELECT COALESCE(SUM(amount_cents),0) FROM credit_movements WHERE client_id=?',(pr['client_id'],)).fetchone()[0]
            if amount_cents>balance:raise HTTPException(409,'Importe supera saldo; conciliacion manual')
            c.execute('INSERT INTO credit_movements(client_id,sale_id,kind,amount_cents,created_at) VALUES(?,?,?,?,?)',
                      (pr['client_id'],None,'ABONO_PEY',-pr['amount_cents'],now()))
            c.execute('UPDATE payment_requests SET status=?,confirmed_at=?,pey_transaction_id=? WHERE id=?',
                      ('PAGADA',now(),txid,pr['id']))
            client=c.execute('SELECT name FROM clients WHERE id=?',(pr['client_id'],)).fetchone()
            for role,msg in (('dueno',f'Abono PEY verificado #{pr["id"]} por ${amount_cents/100:,.2f} de {client["name"]}.'),
                             ('empleado',f'Abono PEY confirmado #{pr["id"]}.'),
                             ('cliente',f'Abono PEY #{pr["id"]} confirmado.')):
                c.execute('INSERT INTO notifications(role,message,created_at) VALUES(?,?,?)',(role,msg,now()))
            result={'ok':True,'type':'credit','status':'PAGADA','id':pr['id']}
        c.execute('INSERT INTO webhook_events VALUES(?,?)',(webhook_id,now()))
        return result

@app.post('/webhooks/pey')
async def pey_webhook(request:Request):
    if not LIVE:raise HTTPException(503,'PEY real no activado')
    raw=await request.body()
    if len(raw)>32768:raise HTTPException(413,'Webhook demasiado grande')
    if not check_standard_webhook(request.headers,raw):raise HTTPException(401,'Firma PEY invalida')
    try:payload=json.loads(raw)
    except (ValueError,TypeError):raise HTTPException(400,'JSON invalido')
    if not isinstance(payload,dict):raise HTTPException(400,'Formato invalido')
    verify_pey_transaction(payload)
    return reconcile_payment(payload,request.headers['webhook-id'])

@app.get('/r/{token}',response_class=HTMLResponse)
def receipt(token:str):
    with db() as c:
        s=c.execute('SELECT id,amount_cents,charged_cents,status,paid_at FROM sales WHERE receipt_token=?',(token,)).fetchone()
    if not s:raise HTTPException(404,'Comprobante no encontrado')
    style="body{font-family:system-ui;background:#f5f8f6;color:#183a31;margin:2rem auto;max-width:380px;padding:1.5rem}.card{background:white;border-radius:18px;padding:1.5rem;box-shadow:0 8px 25px #19332322}small{color:#64796e}.mono{font-family:monospace}.warn{color:#a45518}"
    status={'PAGADA':'PAGO CONFIRMADO POR PEY','PAGADA_PRUEBA':'PAGO PEY DE PRUEBA CONFIRMADO · NO LIQUIDA EL CARRITO','DEMO_PAGADA':'SIMULACIÓN · NO ES COMPROBANTE DE PAGO REAL','PENDIENTE':'PAGO PENDIENTE','FIADA':'VENTA A FIADO · AÚN NO PAGADA','CANCELADA':'VENTA CANCELADA'}.get(s['status'],s['status'])
    return HTMLResponse(f'<html lang="es"><meta name="viewport" content="width=device-width,initial-scale=1"/><style>{style}</style><body><div class="card"><h2>🧾 Tiendita Inteligente</h2><h3>Venta #{s["id"]}</h3><h1>${s["charged_cents"]/100:,.2f} MXN cobrado</h1><p>Carrito: ${s["amount_cents"]/100:,.2f} MXN</p><p class="warn"><strong>{status}</strong></p><small>Consulta la condición de esta venta con la tienda. Este recibo no es un CFDI.</small></div></body></html>')


# ══════════════════ MÓDULO DE FIADOS — DEMOSTRACIÓN ════════════════════
# No envía mensajes ni hace cargos reales. Es un libro de deudas de prueba.
class ClientIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default='', max_length=15)
    credit_limit_cents: int = Field(ge=1, le=10_000_000)

@app.post('/api/clients')
def add_client(item:ClientIn):
    phone=item.phone.strip()
    if phone and (not phone.isdigit() or len(phone)!=10):
        raise HTTPException(400,'Celular: indica 10 dígitos o déjalo vacío')
    with conn_guard, db() as c:
        cur=c.execute('INSERT INTO clients(name,phone,credit_limit_cents,created_at) VALUES(?,?,?,?)',
                      (item.name.strip(),phone,item.credit_limit_cents,now()))
    return {'id':cur.lastrowid,'name':item.name.strip()}

class CreditSaleIn(BaseModel):
    client_id: int = Field(ge=1)

@app.post('/api/sales/{sid}/credit')
def mark_credit_sale(sid:int, req:CreditSaleIn):
    with conn_guard,db() as c:
        c.execute('BEGIN IMMEDIATE')
        sale=c.execute('SELECT * FROM sales WHERE id=?',(sid,)).fetchone()
        client=c.execute('SELECT * FROM clients WHERE id=?',(req.client_id,)).fetchone()
        if not sale: raise HTTPException(404,'Venta no existe')
        if not client: raise HTTPException(404,'Cliente no existe')
        if sale['status']!='PENDIENTE' or sale['qr_id']:
            raise HTTPException(409,'Solo se puede fiar una venta pendiente sin QR')
        balance=c.execute('SELECT COALESCE(SUM(amount_cents),0) FROM credit_movements WHERE client_id=?',
                          (req.client_id,)).fetchone()[0]
        if balance+sale['amount_cents']>client['credit_limit_cents']:
            raise HTTPException(409,'El fiado excede el límite acordado con este cliente')
        try: consume_stock(c,sale,'FIADA',None)
        except ValueError as e: raise HTTPException(409,str(e))
        c.execute('INSERT INTO credit_movements(client_id,sale_id,kind,amount_cents,created_at) VALUES(?,?,?,?,?)',
                  (req.client_id,sid,'FIADO',sale['amount_cents'],now()))
        c.execute('INSERT INTO notifications(role,message,created_at) VALUES(?,?,?)',
                  ('dueno',f'Fiado registrado a {client["name"]}: ${sale["amount_cents"]/100:,.2f}; aún no es pago.',now()))
    return {'status':'FIADA','client_id':req.client_id,'debt_cents':sale['amount_cents']}

class CollectIn(BaseModel):
    amount_cents: int = Field(ge=1,le=10_000_000)

class CollectPeyIn(BaseModel):
    amount_cents: int = Field(ge=1,le=10_000_000)
    method: str = Field(default='QR',pattern='^(QR|PUSH)$')

@app.post('/api/clients/{cid}/payment-requests')
def make_collect_request(cid:int, item:CollectPeyIn, request:Request):
    if CONFIG_BLOCKED:raise HTTPException(503,'Modo PEY bloqueado: configuracion incompleta')
    with conn_guard,db() as c:
        c.execute('BEGIN IMMEDIATE')
        client=c.execute('SELECT * FROM clients WHERE id=?',(cid,)).fetchone()
        if not client:raise HTTPException(404,'Cliente no existe')
        balance=c.execute('SELECT COALESCE(SUM(amount_cents),0) FROM credit_movements WHERE client_id=?',
                          (cid,)).fetchone()[0]
        if item.amount_cents>balance:raise HTTPException(409,'Monto supera saldo del cliente')
        if LIVE and item.method=='PUSH' and (len(client['phone'])!=10 or not client['phone'].isdigit()):
            raise HTTPException(400,'El cliente debe tener un celular de 10 digitos para CoDi Push')
        if LIVE and c.execute("""SELECT 1 FROM payment_requests WHERE client_id=? AND
                      pey_method IN ('REAL_QR','REAL_PN') AND status IN ('PENDIENTE','INICIANDO','REVISAR_PEY') LIMIT 1""",(cid,)).fetchone():
            raise HTTPException(409,'Hay un cobro PEY anterior sin conciliar para este cliente')
        token=secrets.token_urlsafe(24)
        method=('REAL_'+('QR' if item.method=='QR' else 'PN')) if LIVE else 'DEMO'
        cur=c.execute('INSERT INTO payment_requests(client_id,amount_cents,status,token,created_at,pey_method) VALUES(?,?,?,?,?,?)',
                      (cid,item.amount_cents,'INICIANDO' if LIVE else 'PENDIENTE',token,now(),method))
        pid=cur.lastrowid
        if LIVE and pid>9999999:raise HTTPException(400,'Referencia CoDi fuera de rango')
    link=str(request.base_url).rstrip('/')+'/p/'+token
    if not LIVE:
        return {'id':pid,'mode':'DEMO','method':item.method,'link':link,
                'qr_image':qr_png_data(link),'amount_cents':item.amount_cents,
                'message':'SOLICITUD DEMO: no envia cobros ni mensajes'}
    try:
        params=payment_params(item.amount_cents,pid,f'Tiendita abono {pid}','credit')
        if item.method=='QR':
            provider=pey.create_qr(params)
            qr_image=qr_png_data(provider['qrString'])
        else:
            provider=pey.create_push({**params,'phoneNumber':client['phone']})
    except PeyError as exc:
        with conn_guard,db() as c:c.execute('UPDATE payment_requests SET status=? WHERE id=?',('REVISAR_PEY',pid))
        raise HTTPException(502,f'Solicitud incierta PEY ({exc.code}). Revisar antes de reintentar.')
    with conn_guard,db() as c:
        if item.method=='QR':
            c.execute('UPDATE payment_requests SET status=?,pey_qr_id=?,pey_qr_string=? WHERE id=?',
                      ('PENDIENTE',provider['id'],provider['qrString'],pid))
            return {'id':pid,'mode':'REAL','method':'QR','qr_image':qr_image,'link':link,
                    'amount_cents':item.amount_cents,'message':'PEY genero QR CoDi. Esperar pago bancario verificado.'}
        c.execute('UPDATE payment_requests SET status=?,pey_transaction_id=?,pey_codi_id=? WHERE id=?',
                  ('PENDIENTE',provider['transactionId'],provider['codiId'],pid))
        return {'id':pid,'mode':'REAL','method':'PUSH','link':link,'amount_cents':item.amount_cents,
                'message':'CoDi Push enviado por PEY. Aun no pagado.'}

@app.post('/api/payment-requests/{request_id}/demo-confirm')
def confirm_credit_payment_demo(request_id:int):
    if LIVE or CONFIG_BLOCKED:raise HTTPException(403,'Simulacion no habilitada con PEY real o incompleto')
    with conn_guard,db() as c:
        c.execute('BEGIN IMMEDIATE')
        pr=c.execute('SELECT * FROM payment_requests WHERE id=?',(request_id,)).fetchone()
        if not pr:raise HTTPException(404,'Solicitud no existe')
        if pr['status']!='PENDIENTE':raise HTTPException(409,'Solicitud ya procesada')
        client=c.execute('SELECT * FROM clients WHERE id=?',(pr['client_id'],)).fetchone()
        balance=c.execute('SELECT COALESCE(SUM(amount_cents),0) FROM credit_movements WHERE client_id=?',
                          (pr['client_id'],)).fetchone()[0]
        if pr['amount_cents']>balance:raise HTTPException(409,'Deuda insuficiente para confirmar abono')
        c.execute('INSERT INTO credit_movements(client_id,sale_id,kind,amount_cents,created_at) VALUES(?,?,?,?,?)',
                  (pr['client_id'],None,'ABONO_DEMO',-pr['amount_cents'],now()))
        c.execute('UPDATE payment_requests SET status=?,confirmed_at=? WHERE id=?',
                  ('DEMO_PAGADA',now(),request_id))
        for role,message in (
            ('dueno',f'ABONO SIMULADO de {client["name"]}: ${pr["amount_cents"]/100:,.2f}. Sin dinero real.'),
            ('empleado',f'Abono # {request_id} simulado: registra la conciliación, no un pago real.'),
            ('cliente',f'Solicitud #{request_id}: simulación de pago completada. No es recibo bancario.')
        ):
            c.execute('INSERT INTO notifications(role,message,created_at) VALUES(?,?,?)',(role,message,now()))
    return {'ok':True,'status':'DEMO_PAGADA','balance_cents':balance-pr['amount_cents']}

@app.get('/p/{token}',response_class=HTMLResponse)
def public_payment_request(token:str):
    with db() as c:
        pr=c.execute('SELECT * FROM payment_requests WHERE token=?',(token,)).fetchone()
    if not pr:raise HTTPException(404,'Solicitud no encontrada')
    mode=pr['pey_method'] or 'DEMO'
    status=pr['status']
    if mode=='REAL_QR' and pr['pey_qr_string']:
        img=qr_png_data(pr['pey_qr_string'])
        body=f'<img alt="QR CoDi de PEY" style="width:min(90%,300px)" src="data:image/png;base64,{img}">'
        msg='Escanea este QR desde tu aplicacion bancaria compatible con CoDi. Se confirmara cuando el banco reporte el pago.'
    elif mode=='REAL_PN':
        body='<p>Solicitud CoDi Push enviada al celular bancario registrado.</p>'
        msg='Abre tu aplicacion bancaria y autoriza el cobro si estas de acuerdo. No hay pago hasta confirmacion.'
    else:
        body='<p>DEMO — enlace NO pagable.</p>'
        msg='Esta es una simulacion; no realiza pagos bancarios.'
    if status=='PAGADA':msg='Abono bancario verificado. Si necesitas comprobante fiscal solicitalo a tu comercio.'
    elif status=='DEMO_PAGADA':msg='Abono simulado. No se recibio dinero.'
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Tiendita · Solicitud</title></head><body style="background:#f3f7f2;font-family:system-ui;max-width:480px;margin:30px auto;padding:18px;color:#153a30">
      <main style="background:white;padding:24px;border-radius:18px;text-align:center"><h2>Tiendita Inteligente</h2>
      <h1>${pr['amount_cents']/100:,.2f} MXN</h1><p><b>{html_escape(status)}</b></p>{body}
      <p>{html_escape(msg)}</p><small>Solicita ayuda a la tienda para aclarar el estado. Este aviso no es un CFDI.</small>
      </main></body></html>""")
