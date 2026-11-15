"""Build an auditable catalog resource; never writes the app database."""
import csv,json,re,unicodedata,statistics,hashlib,sys
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]
def norm(s):
 s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
 return ' '.join(re.findall(r'[a-z0-9]+',s))
def dump(name,rows):
 rows=list(rows)
 if not rows:return
 with (ROOT/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def quantity(s):
 m=re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|lt|l)(?:\b|\.)',s.lower())
 if not m:return None
 n=float(m[1].replace(',','.'));u=m[2]
 return (round(n*(1000 if u in ('kg','lt','l') else 1),3),'g' if u in ('kg','gr','g') else 'ml')
if len(sys.argv)>1:
 obs={}; manifest=[]
 for file in sorted(Path(sys.argv[1]).glob('*.csv')):
  if file.name=='03-2026_Q2.csv':continue # incomplete archive member
  sha=hashlib.sha256(file.read_bytes()).hexdigest();count=0
  for r in csv.DictReader(file.open(encoding='utf-8-sig')):
   count+=1
   key=tuple(r[k] for k in ('producto','presentacion','marca','categoria'))
   o=obs.setdefault(key,{'dates':set(),'values':[],'local':[],'n':0,'latest':''})
   d=r['fecha_registro'];v=float(r['precio']);o['n']+=1;o['dates'].add(d)
   if d>o['latest']:o['latest']=d;o['values']=[];o['local']=[]
   if d==o['latest']:
    o['values'].append(v)
    if norm(r['estado']) in ('ciudad de mexico','mexico','estado de mexico','distrito federal'):o['local'].append(v)
  manifest.append({'archivo':file.name,'sha256':sha,'filas':count})
 out=[]
 for i,(k,v) in enumerate(sorted(obs.items()),1):
  vals=v['local'] or v['values']
  out.append(dict(profeco_id=f'QQP-{i:05}',producto=k[0],presentacion=k[1],marca=k[2],categoria=k[3],precio_mediana_mxn=statistics.median(vals),precio_min_mxn=min(vals),precio_max_mxn=max(vals),fecha_precio=v['latest'],ambito_precio='CDMX/Edomex' if v['local'] else 'Nacional',observaciones_fecha=len(vals),observaciones_periodo=v['n'],primera_fecha=min(v['dates']),ultima_fecha=max(v['dates'])))
 dump('profeco-productos.csv',out)
 (ROOT/'raw/profeco-extraccion.json').write_text(json.dumps(manifest,indent=2))
prof=list(csv.DictReader((ROOT/'profeco-productos.csv').open()))
cat=list(csv.DictReader((ROOT/'raw/catalogo-mx.csv').open()))
old=json.loads((ROOT/'raw/productos-existentes.json').read_text())
bycode={r['codigo']:r for r in cat}; coverage=[]
for r in old:
 code=r['codigo']; found=code in bycode;synthetic=code.startswith('750000000000')
 coverage.append(dict(codigo=code,nombre_existente=r['nombre'],en_catalogo_mx=found,nombre_catalogo_mx=bycode.get(code,{}).get('nombre',''),accion='conservado' if found else 'agregado_local',tipo_codigo='demo_sintetico' if synthetic else 'codigo_existente_no_certificado',precio_demo_centavos=r['precio_demo_centavos']))
 if not found:
  new={k:'' for k in cat[0]};new.update(codigo=code,nombre=r['nombre'],fuente='abarpay_local',actualizado='2026-11-15');cat.append(new);bycode[code]=new
# Candidate generation only: exact normalized brand and amount, lexical overlap.
index=defaultdict(list)
for r in prof:
 q=quantity(r['presentacion']);b=norm(r['marca'])
 if q and b not in ('s m','varias','sin marca'):index[(b,q)].append(r)
stop=set('de la el los las con en y a un una para sabor botella bolsa caja lata paquete piezas contenido neto'.split())
candidates=[]
for r in cat:
 b=norm(r['marca']);q=quantity(r['contenido'] or (r['cantidad']+' '+r['unidad'])) or quantity(r['nombre'])
 for p in index.get((b,q),[]):
  a=set(norm(r['nombre']).split())-stop;z=set(norm(p['producto']+' '+p['presentacion']+' '+p['marca']).split())-stop
  score=len(a&z)/max(1,len(a|z))
  if score>=.25:candidates.append(dict(codigo=r['codigo'],nombre=r['nombre'],profeco_id=p['profeco_id'],producto_profeco=p['producto'],presentacion_profeco=p['presentacion'],marca=p['marca'],similitud=round(score,3),estado='requiere_revision',precio_referencia_profeco=p['precio_mediana_mxn'],fecha_precio=p['fecha_precio']))
dump('cruces-candidatos.csv',sorted(candidates,key=lambda r:(r['codigo'],-r['similitud'])))
# Confirmations are a manually reviewed identity map, never selected by score alone.
confirmed=json.loads((ROOT/'confirmaciones.json').read_text()) if (ROOT/'confirmaciones.json').exists() else {}
pmap={r['profeco_id']:r for r in prof}
for r in cat:
 code=r['codigo'];pid=confirmed.get(code,'');p=pmap.get(pid,{})
 r.update(nombre_existente_abarpay=next((o['nombre'] for o in old if o['codigo']==code),''),precio_demo_existente_centavos=next((o['precio_demo_centavos'] for o in old if o['codigo']==code),''),existente_abarpay=code in {o['codigo'] for o in old},tipo_codigo='demo_sintetico' if code in {o['codigo'] for o in old if o['codigo'].startswith('750000000000')} else 'fuente_catalogo_no_certificado',profeco_id=pid,comun_demo=bool(pid),criterio_comun='presencia_profeco_proxy_no_ranking_ventas' if pid else '',precio_observado_mxn=p.get('precio_mediana_mxn',''),fecha_precio=p.get('fecha_precio',''),ambito_precio=p.get('ambito_precio',''),estado_cruce='revisado_marca_presentacion_no_certificacion_gtin' if pid else 'sin_cruce_confirmado')
dump('catalogo-integrado.csv',cat);dump('cobertura-existentes.csv',coverage)
summary=dict(productos_fuente=len(bycode)-sum(not c['en_catalogo_mx'] for c in coverage),productos_finales=len(cat),existentes=len(old),existentes_en_fuente=sum(c['en_catalogo_mx'] for c in coverage),existentes_agregados=sum(not c['en_catalogo_mx'] for c in coverage),identidades_profeco=len(prof),candidatos=len(candidates),cruces_confirmados=len(confirmed))
(ROOT/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(summary)
