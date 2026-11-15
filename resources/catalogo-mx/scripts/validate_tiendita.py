#!/usr/bin/env python3
import csv,json
from pathlib import Path
p=Path(__file__).resolve().parents[1]
for source,prefix,key in [('catalogo-integrado.csv','catalogo','codigo'),('profeco-productos.csv','profeco','profeco_id')]:
 original={r[key]:r for r in csv.DictReader((p/source).open())};seen=set()
 for decision in ['incluir','revisar','excluir']:
  for r in csv.DictReader((p/'tiendita'/f'{prefix}-{decision}.csv').open()):
   assert r[key] not in seen;seen.add(r[key])
   assert r['decision_tiendita']==decision
   assert all(r[k]==v for k,v in original[r[key]].items()),r[key]
 assert seen==set(original)
r=list(csv.DictReader((p/'tiendita/catalogo-incluir.csv').open()))
assert sum(x['existente_abarpay']=='True' for x in r)==10
assert sum(x['tipo_codigo']=='demo_sintetico' for x in r)==5
assert sum(bool(x['precio_observado_mxn']) for x in r)==16
assert len(r)==9421
print('OK: particiones exhaustivas y disjuntas; todos los campos originales intactos; 10 existentes, 5 sintéticos, 16 precios vinculados, 9,421 incluidos.')
