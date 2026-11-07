"""Cliente PEY basado en documentos oficiales (2026-11). Sin credenciales en código.
Usar exclusivamente desde backend. No ejecutar contra producción sin autorización explícita.
"""
import base64, binascii, hashlib, hmac, json, time, re, urllib.request, urllib.error
from decimal import Decimal, InvalidOperation

class PeyError(Exception):
    def __init__(self,code='UPSTREAM_ERROR'):
        self.code=code
        super().__init__(code)

def money_to_cents(value):
    if isinstance(value,bool) or value is None:raise ValueError('invalid')
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount<0 or amount.as_tuple().exponent < -2:raise ValueError('invalid')
        cents=amount*100
        if cents!=cents.to_integral_value():raise ValueError('invalid')
        return int(cents)
    except (InvalidOperation, ValueError, TypeError) as e:raise ValueError('invalid') from e

def verify_standard_webhook(headers, raw, secret, tolerance_seconds=300):
    id_=headers.get('webhook-id','')
    ts=headers.get('webhook-timestamp','')
    sigs=headers.get('webhook-signature','')
    if not id_ or not ts or not sigs or not secret.startswith('whsec_'):return False
    try:
        stamp=int(ts)
        if abs(int(time.time())-stamp)>tolerance_seconds:return False
        secret_bytes=base64.b64decode(secret[6:],validate=True)
        message=f'{id_}.{ts}.'.encode('utf-8')+raw
        digest=base64.b64encode(hmac.new(secret_bytes,message,hashlib.sha256).digest()).decode('ascii')
        signatures=[x[3:] for x in sigs.split() if x.startswith('v1,')]
        return any(hmac.compare_digest(digest,s) for s in signatures)
    except (ValueError,TypeError,binascii.Error):return False

class PeyClient:
    BASE='https://api.pey.mx'
    def __init__(self,api_key:str):
        if not api_key:raise PeyError('NO_KEY')
        self.api_key=api_key
    def call(self,method,path,body=None):
        # Sin redireccion a dominios configurables ni URL derivadas del cliente.
        if not path.startswith('/') or '://' in path:raise PeyError('PATH_REJECTED')
        data=json.dumps(body).encode('utf-8') if body is not None else None
        req=urllib.request.Request(self.BASE+path,data=data,method=method,
              headers={'Authorization':'Bearer '+self.api_key,'Accept':'application/json',
                       'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=18) as resp:
                result=json.load(resp)
            if not isinstance(result,dict):raise PeyError('INVALID_RESPONSE')
            return result
        except urllib.error.HTTPError as exc:
            raise PeyError('HTTP_'+str(exc.code)) from exc
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
            raise PeyError('NETWORK_OR_RESPONSE_UNKNOWN') from exc
    def create_qr(self,body):
        result=self.call('POST','/codi/qr',body)
        if not isinstance(result.get('id'),str) or not isinstance(result.get('qrString'),str):
            raise PeyError('QR_SCHEMA_UNKNOWN')
        return result
    def create_push(self,body):
        result=self.call('POST','/codi/pn',body)
        if not isinstance(result.get('transactionId'),str) or not isinstance(result.get('codiId'),str):
            raise PeyError('PUSH_SCHEMA_UNKNOWN')
        return result
    def qr_transactions(self,qr_id):
        if not isinstance(qr_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',qr_id):
            raise PeyError('INVALID_QR_ID')
        return self.call('GET','/transaction/codi/qr/'+qr_id)
    def transaction(self,txid):
        if not txid.isalnum() or len(txid)>50:raise PeyError('INVALID_TXID')
        return self.call('GET','/transaction/'+txid)
