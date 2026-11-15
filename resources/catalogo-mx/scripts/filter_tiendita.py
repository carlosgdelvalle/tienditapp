#!/usr/bin/env python3
"""Conservative, reproducible merchandising filter; no network or app writes."""
import csv,json,re,unicodedata,collections,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'tiendita'; OUT.mkdir(exist_ok=True)
def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
def hit(pattern,s):return re.search(pattern,s) is not None
RULES=[
('Limpieza',r'\b(detergente|lavatrastes|lavaplatos|cloro|blanqueador|suavizante|pinol|fabuloso|limpiador multiusos|jabon (zote|roma)|fibra para cocina)\b'),
('Higiene básica',r'\b(papel higienico|servilletas|panuelos|toallas? (femeninas?|sanitarias?)|toalla de papel|crema dental|pasta colgate|acondicionador|protectores diarios|panales|pasta dental|cepillo dental|jabon (de tocador|neutro|en barra)|shampoo|champu|desodorante|rastrillos?)\b'),
('Mascotas',r'\b(whiskas|pedigree|dog chow|cat chow|ganador|alimento (para )?(perro|gato)|croquetas)\b'),
('Básicos domésticos',r'\b(cerillos|encendedor|pilas electricas|pilas alcalinas|bolsas (de|para) basura)\b'),
('Helados',r'\b(helado|paleta (helada|solero|magnum)|cornetto)\b'),
('Lácteos y huevo',r'\b(leche|yogur\w*|yoghurt|yogurt|queso|crema acida|crema agria|mantequilla|margarina|huevo|producto lacteo|bebida lactea|yakult|danonino)\b'),
('Embutidos',r'\b(jamon|salchicha|mortadela|chorizo|longaniza|tocino)\b'),
('Pan, galletas y tortillas',r'\b(pan (blanco|integral|de caja|tostado|dulce)|panque\w*|galletas?|tortillas?|tostadas?|pastelillos?|mantecadas|canelitas|pinguinos|gansito|submarinos|roles de canela|conchas|donas|habaneras|florentinas)\b'),
('Botanas',r'\b(papas (fritas|adobadas)|botana\w*|cacahuates?|palomitas|frituras?|totopos|chicharron|doritos|sabritas|ruffles|cheetos|takis|churrumais|fritos|rancheritos|chips|tostitos)\b'),
('Dulces y chocolates',r'\b(chocolate\w*|caramelos?|gomitas|mazapan|chicles?|bombones|paleta (de caramelo|payaso)|dulces?|kit ?kat|snickers|milky way|pelon pelo rico|bubbaloo|panditas)\b'),
('Bebidas sin alcohol',r'\b(refresco|coca.cola|pepsi|fanta|sprite|squirt|jarritos|agua (natural|mineral|purificada)|jugo|nectar|bebida (energetica|isotonica|de frutas)|gatorade|powerade|electrolit|boing|jumex)\b'),
('Abarrotes y conservas',r'\b(arroz|frijol\w*|lentejas|garbanzos|alubias|haba\w*|avena|cereal\w*|harina|azucar|sal (de mesa|yodada|refinada)|aceite (vegetal|de soya|de canola|de maiz|comestible)|pasta|spaghetti|espagueti|sopa|fideo|atun|sardinas?|chiles?|salsa|pure de tomate|mayonesa|mostaza|catsup|ketchup|mermelada|pina en almibar|coctel de frutas|flan|piloncillo|cajeta|empanizador|froot loops|choco milk|endulzante|sal de mar|gelatina|cafe|nescafe|te |miel|vinagre|maiz pozolero|elote|chicharos|consome|mole|crema de cacahuate|polvo para hornear)\b'),
]
BLOCK=r'\b(capsulas?|tabletas? de|medicamento|ibuprofeno|paracetamol|aderogyl|dimacol|motrin|colageno|suplemento|creatina|whey|protein powder|proteina en polvo|mct oil|matcha|keto\w*|ketopia|locion|perfume|maquillaje|labial|serum|tinte|bloqueador|protector solar|tiras reactivas|pollo rostizado|filete|bistec|costilla|camaron|salmon|tilapia|carne molida|sushi|pizza|lasagna|lasana|raviol\w*|pesto|quinoa|quinoa|caviar|mejillones|ostiones|pulpo|pavo entero|whisky|whiskey|tequila|vodka|mezcal|ron|brandy|cerveza|beer|vino|licor|cigarros?|cigarrillos|tabaco|vape\w*)\b'
SPECIAL=r'\b(kirkland|members mark|member.s mark|great value|marketside|extra special|chedraui|aurrera|selecto brand|hill country|costco|trader joe|whole foods|organic|organico|gourmet|artesanal|vegano|vegan|tofu|almendra|soya texturizada)\b'
def classify(r,prof=False):
 name=r.get('producto',r.get('nombre','')); s=norm(name+' '+r.get('marca','')+' '+r.get('presentacion',r.get('contenido','')))
 if r.get('existente_abarpay')=='True':return 'incluir','Inventario previo','conservacion_solicitada'
 if hit(r'\b(dermatologico|medicado|lancetas|histiacil|malgadrato|dimeticona|creatine|wp100)\b',s):return 'excluir','Fuera de alcance','medicina_o_suplemento'
 if hit(r'\b(cubitos de atun|atun fresco|atun congelado)\b',s):return 'excluir','Fuera de alcance','pescado_no_conserva'
 if hit(r'\b(picard|nutrisa|vitali|golden hills)\b',s):return 'revisar','Nicho','linea_especializada_o_supermercado'
 if hit(r'\b(mantequilla de coco|pay de queso tortuga)\b',s):return 'revisar','Nicho','variante_especializada'
 if hit(r'costilla jugosa',s) and hit(r'knorr',s):return 'incluir','Abarrotes y conservas','condimento_no_carne'
 if hit(BLOCK,s):return 'excluir','Fuera de alcance','especializado_regulado_o_comida_preparada'
 if prof and r['categoria'] in ['Medicamentos','Arts. de Esparcimiento (Juguetes)','Material Escolar','Aparatos Eléctricos','Aparatos Electrónicos','Artículos Deportivos','Carne y Vísceras de Res','Carne y Vísceras de Cerdo','Carne de Ave','Pescados y Mariscos','Frutas Frescas','Hortalizas Frescas']:
  return 'excluir','Fuera de alcance','departamento_no_abarrotes_basico'
 if len(norm(name).strip())<3 or not re.search('[a-z]',norm(name)):return 'revisar','Sin clasificar','descripcion_insuficiente'
 # Match the product name first: presentation 'con jugo' does not make mayonnaise juice.
 ordered=sorted(RULES,key=lambda rule: 0 if hit(rule[1],norm(name)) else 1)
 if hit(r'^(xurrikos|pay|galletas|pan |natilla|gelatina)',norm(name)):
  overrides={'xurrikos':'Botanas','pay':'Pan, galletas y tortillas','galletas':'Pan, galletas y tortillas','pan ':'Pan, galletas y tortillas','natilla':'Lácteos y huevo','gelatina':'Abarrotes y conservas'}
  target=next(v for k,v in overrides.items() if norm(name).startswith(k))
  ordered=[(target,r'.')]+ordered
 for cat,pat in ordered:
  if hit(pat,s):
   if hit(SPECIAL,s) or hit(r'\b(precissimo|ley|aprecio|ke precio)\b',norm(r.get('marca',''))):return 'revisar',cat,'marca_supermercado_o_nicho'
   if hit(r'\b(2[0-9]|[3-9][0-9]) rollos\b',s):return 'revisar',cat,'paquete_voluminoso'
   if hit(r'\b([6-9]|[1-9][0-9]+)\s*(kg|kilos|litros|lt|l)\b',s):return 'revisar',cat,'formato_grande'
   if prof and hit(r'granel',s):return 'revisar',cat,'granel_requiere_operacion_especifica'
   return 'incluir',cat,'familia_basica_por_descripcion'
 return 'revisar','Sin clasificar','sin_evidencia_suficiente'
def write(name,rows,fields):
 with (OUT/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
summary={}; samples=[]
for file,key in [('catalogo-integrado.csv','catalogo'),('profeco-productos.csv','profeco')]:
 rows=list(csv.DictReader((ROOT/file).open())); fields=list(rows[0])+['decision_tiendita','familia_tiendita','motivo_filtro']; groups=collections.defaultdict(list)
 for r in rows:
  d,c,m=classify(r,key=='profeco');r.update(decision_tiendita=d,familia_tiendita=c,motivo_filtro=m);groups[d].append(r)
 for d in ['incluir','revisar','excluir']:write(f'{key}-{d}.csv',groups[d],fields)
 summary[key]={'entrada':len(rows),'decisiones':{d:len(v) for d,v in groups.items()},'familias_incluidas':dict(collections.Counter(r['familia_tiendita'] for r in groups['incluir']))}
 for d,rs in groups.items():
  for r in random.Random(20261115).sample(rs,min(30,len(rs))):samples.append({'fuente':key,'id':r.get('codigo',r.get('profeco_id')),'descripcion':r.get('nombre',r.get('producto')),'marca':r['marca'],'presentacion':r.get('contenido',r.get('presentacion')),'decision':d,'familia':r['familia_tiendita']})
 if key=='catalogo':
  assert sum(r['existente_abarpay']=='True' for r in groups['incluir'])==10
  summary[key]['precios_observados_incluidos']=sum(bool(r['precio_observado_mxn']) for r in groups['incluir'])
  summary[key]['sinteticos_conservados']=sum(r['tipo_codigo']=='demo_sintetico' for r in groups['incluir'])
write('muestra-auditoria.csv',samples,list(samples[0]))
(OUT/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
