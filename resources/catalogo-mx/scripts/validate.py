import csv,json,hashlib
from pathlib import Path
p=Path(__file__).resolve().parents[1]
def read(f):return list(csv.DictReader((p/f).open()))
src=read('raw/catalogo-mx.csv');cat=read('catalogo-integrado.csv');cov=read('cobertura-existentes.csv');prof=read('profeco-productos.csv')
assert hashlib.sha256((p/'raw/catalogo-mx.csv').read_bytes()).hexdigest()==json.loads((p/'raw/version.json').read_text())['archivos']['catalogo-mx.csv']['sha256']
assert len(src)==24887 and len(cat)==24893
codes=[x['codigo'] for x in cat];assert len(codes)==len(set(codes));assert all(c['codigo'] in codes for c in cov)
assert len(cov)==10 and sum(c['en_catalogo_mx']=='True' for c in cov)==4
assert sum(c['tipo_codigo']=='demo_sintetico' for c in cat)==5
ps={x['profeco_id']:x for x in prof}
for c in cat:
 if c['profeco_id']:
  assert c['profeco_id'] in ps and c['comun_demo']=='True'
  assert c['precio_observado_mxn']==ps[c['profeco_id']]['precio_mediana_mxn']
 else:assert c['precio_observado_mxn']=='' and c['comun_demo']=='False'
assert sum(bool(c['profeco_id']) for c in cat)==21
assert all(x['ultima_fecha']<='2026/03/13' for x in prof)
print('OK: source SHA256, counts, uniqueness, existing-code coverage, synthetic flags, reviewed links and price provenance')
