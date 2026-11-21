# 02 · Contratos y tenencia (multi-tenant sobre PostgreSQL con RLS)

Estado: paquete de handoff para el equipo DSH. Redactado 21-nov-2026. Instrucciones de implementación para producción; no modifica el código del demo actual.

## Propósito

Convertir el backend demo de una sola tienda (FastAPI + SQLite, una conexión por petición) en un servicio multi-tenant sobre PostgreSQL, con aislamiento a nivel de fila (RLS) y pertenencia de usuario a tenant. La identidad de los usuarios (Auth0 y Microsoft Entra ID) vive en `04-identidad-onboarding-y-pey.md` y este documento la consume.

## Contexto heredado

- El demo guarda una sola tienda `tiendita-esquina` y tres empleados en SQLite (`server/db.py`, contrato `docs/v1-contract.md`).
- El acceso es simulado con el header `X-Employee-Id` y la consola usa un PIN compartido (`docs/decisiones/0005-v1-android-backend-consola.md`).
- La regla de que solo `apply_payment` marca una venta PEY como pagada se conserva en producción (`server/payments.py`).

## Decisiones de diseño

- Una tienda equivale a un tenant. La relación es 1 a 1 y se impone en el esquema.
- Un usuario dueño puede ser miembro de varios tenants independientes. Cada tenant es un negocio aislado.
- La unidad de aislamiento es `tenant_id`. RLS filtra por tenant en cada tabla de negocio.
- El backend usa un único rol de base de datos `abarpay_app` y fija el contexto por transacción con las variables `app.tenant_id` y `app.user_id`.
- Ninguna consulta de la aplicación usa el rol superusuario ni el owner de las tablas.

## Modelo de datos

| Tabla | Propósito | Clave de aislamiento |
| --- | --- | --- |
| `tenants` | Negocio (1 a 1 con su tienda) | PK `id` |
| `stores` | Punto de venta, único por tenant | `tenant_id` UNIQUE |
| `users` | Identidad única de una persona | PK `id` |
| `memberships` | Relación usuario-tenant con rol y permisos | `tenant_id`, `user_id` |
| `invites` | Invitaciones pendientes con token hasheado | `tenant_id` |
| Tablas de negocio | `products`, `sales`, `sale_items`, `payments`, `inventory_movements`, `fiado_customers`, `fiado_entries`, `fiado_drafts`, `expenses`, `day_tasks`, `bank_accounts`, `purchase_orders`, `receipts`, `till_shifts`, `outbox_applied` | `tenant_id` |

```sql
CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  name text NOT NULL,
  legal_name text NOT NULL DEFAULT '',
  rfc text,
  country text NOT NULL DEFAULT 'MX',
  timezone text NOT NULL DEFAULT 'America/Mexico_City',
  status text NOT NULL CHECK (status IN ('active','suspended','closed')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL UNIQUE REFERENCES tenants(id),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  name text NOT NULL DEFAULT '',
  idp text NOT NULL CHECK (idp IN ('auth0','entra','legacy')),
  external_sub text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (idp, external_sub)
);

CREATE TABLE memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  role text NOT NULL CHECK (role IN ('owner','employee')),
  can_sell boolean NOT NULL DEFAULT false,
  can_fiado boolean NOT NULL DEFAULT false,
  can_inventory boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, user_id)
);

CREATE TABLE invites (
  token_hash text PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  email text,
  role text NOT NULL CHECK (role IN ('owner','employee')),
  can_sell boolean NOT NULL DEFAULT false,
  can_fiado boolean NOT NULL DEFAULT false,
  can_inventory boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  revoked_at timestamptz
);
```

- `users.idp = 'legacy'` existe solo para preservar el historial de los empleados del demo durante la migración. Esas filas son históricas y nunca se vinculan automáticamente a un inicio de sesión real. Un inicio de sesión real crea su propio `users`.
- `UNIQUE (tenant_id)` en `stores` impone la relación 1 a 1. Cada tenant tiene a lo sumo una tienda y cada tienda pertenece a un solo tenant.
- El token de invitación se genera con 32 bytes aleatorios, se muestra una sola vez y se persiste como `SHA-256(token)` en `token_hash`. El token en claro nunca se guarda ni se registra.

## Prevención de claves foráneas entre tenants

Cada tabla padre declara `UNIQUE (tenant_id, id)` y las claves foráneas son compuestas, de modo que una fila solo puede referenciar otra del mismo tenant.

```sql
ALTER TABLE stores ADD CONSTRAINT stores_tenant_id_id_key UNIQUE (tenant_id, id);
ALTER TABLE products ADD CONSTRAINT products_tenant_id_id_key UNIQUE (tenant_id, id);

CREATE TABLE sales (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  store_id uuid NOT NULL,
  employee_id uuid NOT NULL,
  status text NOT NULL,
  total_cents integer NOT NULL,
  charged_cents integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  occurred_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id),
  FOREIGN KEY (tenant_id, store_id) REFERENCES stores (tenant_id, id)
);

CREATE TABLE sale_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  sale_id uuid NOT NULL,
  product_id uuid NOT NULL,
  qty_milli integer NOT NULL,
  unit_price_cents integer NOT NULL,
  line_total_cents integer NOT NULL,
  FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id),
  FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id)
);
```

## Aislamiento con RLS

### Rol y variables de contexto

```sql
CREATE ROLE abarpay_app NOLOGIN;
-- El rol de conexión LOGIN, sin privilegios administrativos, asume abarpay_app.
-- El migrador es otro principal. El rol de servicio carece de BYPASSRLS y DDL.
```

Cada petición autorizada abre una transacción y fija el contexto antes de cualquier consulta:

```python
def set_tenant_context(conn, *, tenant_id: str, user_id: str) -> None:
    conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
```

El tercer argumento `true` equivale a `SET LOCAL`. El valor local se revierte al terminar o abortar la transacción. Bloquear valores de sesión globales; probar reutilización con commit y rollback. NULLIF cubre también el marcador vacío de una conexión reutilizada.

### Política canónica

```sql
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE stores FORCE ROW LEVEL SECURITY;

CREATE POLICY store_tenant_isolation ON stores FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

La misma política se aplica a cada tabla de negocio, cambiando solo el nombre. Reglas:

- `current_setting('app.tenant_id', true)` devuelve `NULL` cuando la variable no está fijada. La comparación con `NULL` es `NULL`, y una fila con `NULL` se filtra. El resultado es denegación por defecto: sin contexto no se lee ni se escribe nada.
- `FORCE ROW LEVEL SECURITY` evita que el owner de la tabla salte la política.
- Las políticas `FOR ALL` cubren lectura y escritura con `USING` y `WITH CHECK`, de modo que un `INSERT` o `UPDATE` que intente escribir otra `tenant_id` falla, no se filtra en silencio.

### Políticas auxiliares

```sql
-- Un usuario ve su propio registro.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_self_read ON users FOR SELECT
  USING (id = NULLIF(current_setting('app.user_id', true), '')::uuid);

-- Un usuario ve sus propias pertenencias; el dueño las administra con la capa
-- de aplicación mediante una función SECURITY DEFINER limitada a ese propósito.
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_self_read ON memberships FOR SELECT
  USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid);

ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;
```

El alta atómica crea tenant, tienda y dueño o revierte todo. Fijar contexto de usuario desde identidad verificada para consultar sus memberships y seleccionar tenant. La API de selección rechaza tiendas ajenas aun si el solicitante conoce el UUID. Resolver la identidad OIDC por emisor y sujeto con una operación restringida de bootstrap; el token no proporciona permisos de tabla.

La administración de `memberships` e `invites` la resuelve el endpoint de dueño con una función `SECURITY DEFINER` limitada a ese propósito, con identidad de ejecución mínima, nombres de esquema calificados, search_path fijo y EXECUTE revocado a PUBLIC. Validar rol y tenant dentro de cada operación. Probar que una llamada directa no asigna un dueño o pertenencia ajena.

## Migración SQLite → PostgreSQL

La migración es una utilidad de una sola ejecución, idempotente y con `--dry-run`:

1. Crear esquema y aplicar RLS.
2. Inventariar las tiendas y asignar la tienda demo expresamente identificada a su tenant demo; para esa tienda, crear `tenants` y su `stores` (1 a 1) y propagar `tenant_id` a todas las filas de negocio.
3. Crear `users` históricos con `idp='legacy'` para **todos** los empleados presentes en la copia de corte, incluidos inactivos, y sus `memberships` con los permisos equivalentes de v2. Nunca se reclaman automáticamente.
4. Reasignar `employee_id` y referencias de claves foráneas a los nuevos UUID sin perder movimientos de inventario ni pagos.
5. Verificar conteos por tabla contra la base SQLite y emitir un reporte de diferencias.

La base SQLite queda solo como fuente de la migración. La base activa de producción pasa a ser PostgreSQL y nunca se escribe SQLite después del corte.

## Contratos de tenencia (API)

Las operaciones de membresía exigen identidad verificada. Emitir invitaciones sólo a empleados con permisos seleccionados; la aceptación no permite elevar el rol. Proteger al último dueño de la tienda. Para seleccionar tienda, GET /api/me/memberships enumera sólo pertenencias activas del usuario y POST /api/session/store verifica la elegida antes de rotar la sesión. El tenant seleccionado nunca se confía a un header de identidad del cliente. El dueño se identifica por su `membership.role = 'owner'`.

- `GET /api/tenant` → `{id, slug, name, legalName, rfc, timezone, status, store:{id, name}}` del tenant del token.
- `GET /api/tenant/members` (owner) → `{items:[{userId, email, name, role, canSell, canFiado, canInventory, active}]}`.
- `POST /api/tenant/members/invite` (owner) body `{email?, role, canSell, canFiado, canInventory}` → `{token, url}`.
- `GET /api/tenant/members/invites/{token}` → datos mínimos de la invitación (404 expirada o revocada). El token se busca por su hash.
- `POST /api/tenant/members/invites/{token}/accept` → crea la `membership` y devuelve el perfil.
- `PATCH /api/tenant/members/{userId}` (owner) body `{role?, canSell?, canFiado?, canInventory?, active?}`.
- `DELETE /api/tenant/members/{userId}` (owner) → desactiva la pertenencia.

Reglas de autorización:

- `owner`: todo el tenant, incluida la gestión de cuentas bancarias.
- `employee`: solo lo que habilitan `can_sell`, `can_fiado` y `can_inventory`.

## Flujo de contexto por petición

```mermaid
sequenceDiagram
    participant C as Cliente (app/consola)
    participant A as API (FastAPI)
    participant D as PostgreSQL
    C->>A: petición con Bearer token
    A->>A: valida access token (aud, iss, exp) y resuelve user
    A->>A: resuelve membership y tenant_id
    A->>D: BEGIN; set_config('app.tenant_id',...,true)
    A->>D: consulta de negocio (RLS filtra por tenant)
    A->>D: COMMIT (contexto se revierte)
    A->>C: respuesta
```

## Modos de fallo y recuperación

| Fallo | Comportamiento | Recuperación |
| --- | --- | --- |
| Contexto de tenant ausente | RLS devuelve cero filas y los writes fallan | El endpoint exige 401/403 antes de consultar |
| Conexión de pool reutilizada | `SET LOCAL` revierte al terminar la transacción | Prueba que una segunda petición sin contexto no vea filas |
| Intento de escribir otra `tenant_id` | `WITH CHECK` falla la sentencia | Se registra como error 403, sin escritura parcial |
| Clave foránea entre tenants | La FK compuesta falla | Se rechaza la fila sin modificar la base |
| Migración interrumpida | `--dry-run` primero y transacción por tabla | Reejecutar; la idempotencia no duplica filas |
| `current_setting` con nombre no calificado | PostgreSQL rechaza variables sin namespace | Usar siempre `app.tenant_id` y `app.user_id` |

## Criterios de aceptación

- [ ] Dos tenants A y B: `GET /api/tenant` de A no devuelve filas de B en ninguna tabla de negocio.
- [ ] Una consulta directa con `app.tenant_id` sin fijar devuelve cero filas (denegación por defecto).
- [ ] `FORCE ROW LEVEL SECURITY` está activo y `abarpay_app` no es owner ni superusuario.
- [ ] La relación 1 a 1 se impone: un segundo `stores` para el mismo tenant falla.
- [ ] Una clave foránea que apunte a otra `tenant_id` falla.
- [ ] El token de invitación solo se guarda como hash y el token en claro no aparece en la base ni en logs.
- [ ] Un inicio de sesión real nunca reclama automáticamente una fila `legacy`.
- [ ] Un dueño puede pertenecer a varios tenants independientes.
- [ ] La migración de una base SQLite con ventas, movimientos y fiado reproduce los conteos en PostgreSQL.
- [ ] No hay credenciales ni secretos en el esquema, las migraciones ni los logs.

## Puertas

- [ ] Prueba de integración con una instancia PostgreSQL de prueba que ejecute las políticas de dos tenants y los casos negativos.
- [ ] Prueba de regresión que enumera las tablas del esquema y falla si alguna tabla de negocio no tiene RLS habilitado (`pg_class.relrowsecurity = true`) y política de tenant.
- [ ] Prueba de restricciones 1 a 1 y de claves foráneas compuestas entre tenants.
- [ ] Migración `--dry-run` y `--apply` sobre un fixture SQLite en verde, ejecutada dos veces para probar idempotencia.
- [ ] Ejercicio de respaldo y restauración sin pérdida de aislamiento.

## Proveniencia

- CREATE POLICY (PostgreSQL): <https://www.postgresql.org/docs/current/sql-createpolicy.html>
- Contrato v1 heredado: `docs/v1-contract.md`
- Contrato v2 heredado (equipo, permisos, invitaciones): `docs/v2-contract.md`

## Decisiones fijadas

- Una tienda equivale a un tenant (1 a 1). Un usuario dueño puede ser miembro de varios tenants.
- Roles de producción: `owner` y `employee` con los permisos descritos.
- Los tokens de invitación se guardan hasheados y se muestran una sola vez.
