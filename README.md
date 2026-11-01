# Bia Agent Platform

Plataforma interna donde cualquier persona de Bia puede crear un agente de IA a partir de un
catálogo curado de modelos y herramientas. Todo lo que hace cada agente queda registrado:
ejecuciones, pasos, tokens, costo y latencia.

El primer agente construido con la plataforma será el asistente de facturación de servicio al
cliente, que responde con RAG sobre tarifas, procedimientos y preguntas frecuentes.

## Cómo funcionará

Un agente es **configuración declarativa y versionada en la base de datos**, nunca código
generado. Un único runtime genérico lee esa configuración (la *spec*) y la ejecuta.

El flujo para crear un agente, llamado Agent Builder, es:

1. La persona describe en lenguaje natural lo que necesita.
2. La plataforma busca agentes parecidos y un LLM decide si ya existe uno.
3. Si existe, la persona confirma que es el que buscaba.
4. Si no existe, un LLM diseñador propone la spec, eligiendo solo del catálogo y justificando
   sus decisiones.
5. La persona revisa y ajusta la propuesta.
6. Se generan casos de prueba y se corren evals. Por debajo del umbral no se puede publicar.
7. El agente se publica como una spec versionada.

## Estado

| Fase | Tema | Estado |
|---|---|---|
| 0 | Setup y deploy temprano | Terminada |
| 1 | Modelo de datos y base | Terminada |
| 2 | Provider de modelos | Terminada |
| 3 | Catálogos (modelos y herramientas) | Terminada |
| 4 | Trazas | Terminada |
| 5 | Runtime de agentes | Terminada |
| 6 | Registro de agentes | Terminada |
| 7 | RAG | Terminada |
| 8-14 | Builder, evals, frontend y entrega | Pendientes |

Hoy existen la API con `GET /health`, la protección con contraseña, el esquema de base de datos,
el provider de modelos, los catálogos de modelos y herramientas, el registro de trazas, el runtime,
el registro de agentes y las bases de conocimiento con búsqueda citable. El Builder todavía no está construido, así que por ahora los agentes se crean
enviando la spec completa a `POST /agents`. El detalle está en [docs/PLAN.md](docs/PLAN.md).

## Stack

- **Backend:** Python 3.12 y FastAPI.
- **Base de datos:** Supabase (Postgres con pgvector).
- **LLM:** OpenAI, siempre a través de la abstracción `ModelProvider`.
- **Orquestación y trazas:** loop de tool-calling y tablas `runs` / `run_steps` propios.
- **Frontend:** Next.js, en la fase final. Hasta entonces, las demos se hacen en Swagger.

## Estructura

```
backend/bia/     Paquete Python, organizado por verticales (agents, builder, runtime, rag...)
backend/tests/   Pruebas; replica la estructura de bia/
docs/            Plan y modelo de datos
frontend/        Next.js, fase final
```

Las convenciones de código están en [CLAUDE.md](CLAUDE.md).

---

## Guía: fase 0 — Setup y deploy

### Levantar el proyecto en local

Necesitas [uv](https://docs.astral.sh/uv/). Todos los comandos de backend se corren desde
`backend/`.

```bash
cd backend
uv sync
cp .env.example .env
```

Completa `.env`. Cada variable está explicada en [.env.example](backend/.env.example):

| Variable | Requerida | Para qué sirve |
|---|---|---|
| `OPENAI_API_KEY` | Sí | Acceso a OpenAI. |
| `DATABASE_URL` | Sí | Connection string de Supabase (transaction pooler, puerto 6543). |
| `API_ACCESS_PASSWORD` | Sí | Contraseña compartida de la API; mínimo 16 caracteres. |
| `ENVIRONMENT` | Sí | `development`, `test` o `production`. |
| `LOG_LEVEL` | No | Por defecto `INFO`. |

Si falta una variable o no es válida, la app no arranca y el error dice cuál corregir.

### Correr la API

```bash
uv run uvicorn bia.api.main:app --reload
```

- `http://localhost:8000/health` responde sin credenciales.
- `http://localhost:8000/docs` abre Swagger. El navegador pide usuario y contraseña: el usuario
  puede ser cualquiera y la contraseña es `API_ACCESS_PASSWORD`.

Cualquier ruta nueva queda protegida por defecto. Para hacer pública una ruta, agrégala al enum
`PublicPath` en [auth.py](backend/bia/api/auth.py).

### Correr pruebas y lint

```bash
uv run pytest
uv run ruff check .
```

CI corre estos dos comandos en cada push ([ci.yml](.github/workflows/ci.yml)).

### Agregar una dependencia

Usa siempre `uv`; no edites a mano `pyproject.toml` ni `uv.lock`.

```bash
uv add <paquete>
```

### Desplegar el backend

El backend está en Vercel, importado desde este repo con Root Directory `backend/`. El
entrypoint está en `[tool.vercel]` de [pyproject.toml](backend/pyproject.toml).

Carga las variables requeridas en el proyecto de Vercel. Como el entorno es serverless,
`DATABASE_URL` debe apuntar al transaction pooler (puerto 6543). Para verificar el deploy,
abre `/health` en la URL pública.

---

## Guía: fase 1 — Modelo de datos y base

El significado de cada columna está en [docs/data-model.md](docs/data-model.md), la fuente de
verdad del esquema. Hay 13 tablas: catálogos, agentes, conocimiento, trazas, evals y
orquestación.

### Crear o actualizar la base

```bash
uv run python -m bia.database.migrate
```

El comando aplica todos los `table.sql` y los seeds en una sola transacción, usando la
`DATABASE_URL` de `.env`. Se puede correr las veces que quieras.

Solo crea lo que falta: **no modifica tablas que ya existen**. Para cambiar una columna, aplica
el `ALTER` a mano en Supabase y actualiza también el `table.sql` y el modelo de datos.

La extensión `vector` debe estar habilitada en el proyecto de Supabase antes de migrar.

### Agregar una tabla

1. Documenta sus columnas en [docs/data-model.md](docs/data-model.md).
2. Crea `bia/database/queries/<tabla>/table.sql`, con `CREATE TABLE IF NOT EXISTS`, un comentario
   por columna y `ENABLE ROW LEVEL SECURITY`.
3. Agrégala al enum `DatabaseTable` en [loader.py](backend/bia/database/queries/loader.py),
   después de las tablas que referencia. El orden del enum es el orden de creación.
4. Corre `uv run pytest`: las pruebas verifican estas convenciones y el orden.

### Agregar una consulta y ejecutarla

El SQL vive en archivos `.sql`, nunca en strings de Python.

1. Crea `bia/database/queries/<tabla>/<operacion>.sql`, abriendo con un comentario que explique
   por qué existe y quién lo usa.
2. Agrega la operación al enum `SqlOperation` en
   [loader.py](backend/bia/database/queries/loader.py).
3. Ejecútala con parámetros enlazados:

```python
from sqlalchemy import text

from bia.database.connection import database_session, get_engine
from bia.database.queries import DatabaseTable, SqlOperation, load_sql

sql = load_sql(DatabaseTable.AGENTS, SqlOperation.GET_BY_ID)
with database_session(get_engine()) as session:
    row = session.execute(text(sql), {"agent_id": agent_id}).one()
```

Al salir del bloque se hace commit, y si hay una excepción se hace rollback y la excepción se
propaga.

### Cambiar los modelos sembrados o sus precios

1. Edita [models/seed.sql](backend/bia/database/queries/models/seed.sql). Los precios actuales
   se tomaron de la [página de precios de OpenAI](https://developers.openai.com/api/docs/pricing)
   el 2026-10-31.
2. Corre la migración. Las filas existentes se actualizan sin duplicarse, porque se identifican
   por proveedor e id del modelo.

Quitar un modelo del archivo no lo borra de la base.

Para sembrar otra tabla, crea su `seed.sql` idempotente y agrega la tabla a `_SEEDED_TABLES` en
[migrate.py](backend/bia/database/migrate.py).

### Correr las pruebas de integración

Por defecto se omiten, también en CI. Para correrlas, pasa la URL como variable de proceso:

```bash
INTEGRATION_DATABASE_URL="<connection string>" uv run pytest tests/database
```

Estas pruebas crean tablas y siembran filas en esa base. Sin esta variable nunca tocan la base
de `.env`.

---

## Guía: fase 2 — Provider de modelos

Toda llamada a un LLM pasa por el contrato `ModelProvider`
([base.py](backend/bia/providers/base.py)). Fuera de `bia/providers/openai/` no se importa `openai`.

### Llamar a un modelo

El id del modelo sale siempre del catálogo (`provider_model_id`), nunca de un literal en el código.

```python
from bia.providers.artifacts import ChatMessage, MessageRole
from bia.providers.cost import compute_cost
from bia.providers.factory import get_provider

provider = get_provider(catalog_model.provider)
messages = [ChatMessage(role=MessageRole.USER, content="¿Cuál es mi saldo?")]

result = provider.chat(messages, catalog_model.provider_model_id)
cost = compute_cost(result.usage, catalog_model)
```

| Método | Para qué sirve | Qué devuelve |
|---|---|---|
| `chat(messages, model, tools)` | Un turno de conversación, con tools opcionales | `ChatResult` |
| `chat_structured(messages, response_model, model)` | Respuesta validada contra un modelo pydantic | `StructuredChatResult` (la instancia está en `parsed`) |
| `embed(texts, model)` | Embeddings de un lote en una sola llamada | `EmbeddingResult` |

Todos los resultados incluyen `usage` y `latency_ms`, los datos que necesitan las trazas. Si la
llamada falla o la respuesta está truncada, rechazada o vacía, se lanza `ProviderError`.

Los argumentos de un `ToolCall` llegan como el JSON crudo que escribió el modelo, y pueden ser
inválidos. Validarlos le corresponde al runtime.

### Por qué se usa la API de Responses

Con los modelos sembrados, Chat Completions rechaza las tools, así que el provider usa Responses.
Las llamadas van con `store=False` y la conversación se reenvía completa en cada turno.

Estos modelos tampoco aceptan `temperature`, por eso el contrato no la expone.

### Probar código que usa un LLM

Las pruebas nunca llaman a la API real. Usa `FakeModelProvider`
([fake.py](backend/tests/providers/fake.py)) y programa sus respuestas en orden:

```python
from tests.providers.fake import FakeModelProvider

provider = FakeModelProvider()
provider.queue_tool_calls([tool_call])
provider.queue_text("Tu saldo es 100")
```

Si el código hace más llamadas de las programadas, la prueba falla. `provider.chat_requests`
guarda lo que recibió cada llamada.

### Agregar un proveedor

1. Agrega el miembro a `ProviderName` en [artifacts.py](backend/bia/providers/artifacts.py).
2. Crea `bia/providers/<proveedor>/` con una clase que implemente `ModelProvider`.
3. Registra su constructor en `_PROVIDER_BUILDERS`, en
   [factory.py](backend/bia/providers/factory.py).

Las pruebas fallan si un miembro del enum no tiene constructor registrado.

---

## Guía: fase 3 — Catálogos

### Requisito nuevo para arrancar la API

Al arrancar, la API sincroniza las herramientas con la base. Por eso `DATABASE_URL` debe apuntar a
una base ya migrada (`uv run python -m bia.database.migrate`). Si la sincronización falla, la API
no arranca, y `/health` tampoco responde.

### Consultar los catálogos

Con la API corriendo, abre `/docs` o llama a los endpoints con la contraseña compartida:

```bash
curl -u demo:$API_ACCESS_PASSWORD localhost:8000/models
curl -u demo:$API_ACCESS_PASSWORD "localhost:8000/models?only_active=true"
curl -u demo:$API_ACCESS_PASSWORD localhost:8000/models/<id>
curl -u demo:$API_ACCESS_PASSWORD localhost:8000/tools
```

| Endpoint | Qué devuelve |
|---|---|
| `GET /models` | Todos los modelos, ordenados por nombre. Con `only_active=true`, solo los activos. |
| `GET /models/{id}` | Un modelo, activo o no. Responde 404 si no existe. |
| `GET /tools` | Todas las herramientas. Con `only_active=true`, solo las activas. |

### Agregar una herramienta

1. Agrega el nombre al enum `ToolName` en
   [artifacts.py](backend/bia/catalog/tools/artifacts.py).
2. Crea la clase en `bia/catalog/tools/`, heredando de `Tool`
   ([base.py](backend/bia/catalog/tools/base.py)). Toma de ejemplo
   [consultar_factura.py](backend/bia/catalog/tools/consultar_factura.py).
3. Registra su constructor en `_TOOL_BUILDERS`, en
   [registry.py](backend/bia/catalog/tools/registry.py).
4. Reinicia la API: la herramienta aparece en la tabla `tools`.

`run(args, context)` recibe los argumentos ya validados por el runtime y un `ToolContext` con lo que
decide la ejecución y no el modelo, como la base de conocimiento de la spec. Los fallos esperados,
como un cliente inexistente, se devuelven como `ToolResult(error=...)` para que el modelo pueda
reaccionar. Si la herramienta llama a un modelo, debe reportar `model_id`, tokens y costo en su
`ToolResult`, y puede cambiar `step_type`, para que la traza los registre.

### Retirar una herramienta

El código manda sobre la tabla: las herramientas del registry quedan activas y las demás, inactivas.
Para retirar una, quítala del código y reinicia. Su fila se conserva porque los pasos de runs pasados
la referencian. Cambiar `is_active` a mano en Supabase no dura: el siguiente arranque lo sobrescribe.

En cambio, los modelos se administran en la base y en
[models/seed.sql](backend/bia/database/queries/models/seed.sql), y la sincronización no los toca.

### Probar `consultar_factura`

Las facturas son datos falsos, en
[facturas.json](backend/bia/catalog/tools/data/facturas.json): clientes `100001` a `100010`, con
saldo en COP, período, consumo y fecha límite. El cliente `100006` tiene saldo a favor (negativo) y
el `100003` tiene saldo 0.

```python
from bia.catalog.tools.base import ToolContext
from bia.catalog.tools.registry import get_tool
from bia.database.connection import get_engine

context = ToolContext(bind=get_engine(), knowledge_base_id=None)
get_tool("consultar_factura").run({"numero_cliente": "100001"}, context)
```

### Pruebas de esta fase

Las consultas de modelos corren sobre SQLite en cada `uv run pytest`. Las de herramientas usan
funciones de Postgres, así que solo corren con `INTEGRATION_DATABASE_URL`. Solo crean filas dentro
de una transacción que se revierte al final, y no dejan nada en esa base:

```bash
INTEGRATION_DATABASE_URL="<connection string>" uv run pytest tests/catalog/tools/test_repository.py
```

---

## Guía: fase 4 — Trazas

Cada ejecución queda en `runs` y cada uno de sus pasos en `run_steps`. El runtime escribe estas
trazas por sí solo (ver fase 5); usa `RunRecorder` directamente solo si ejecutas LLMs por fuera de él.

### Registrar un run

```python
from bia.database.connection import get_engine
from bia.tracing.artifacts import RunOrigin, RunStepDraft, StepType
from bia.tracing.recorder import RunRecorder

recorder = RunRecorder(get_engine())
run = recorder.start_run(agent_id, agent_version_id, RunOrigin.PLAYGROUND, "¿Cuál es mi saldo?")
recorder.add_step(
    run.id,
    RunStepDraft(
        step_type=StepType.LLM_CALL,
        model_id=catalog_model.id,
        input=[{"role": "user", "content": "¿Cuál es mi saldo?"}],
        output="Tu saldo es 100",
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cost=compute_cost(result.usage, catalog_model),
        latency_ms=result.latency_ms,
    ),
)
recorder.finish_run(run.id, "Tu saldo es 100")
```

Reglas que conviene conocer:

- **Cada escritura hace su propio commit**, separado de la transacción de quien llama. Así, si la
  ejecución se cae, lo ya registrado no se pierde.
- **Todo run se cierra**: `finish_run(run_id, output)` lo marca `succeeded` y
  `fail_run(run_id, error)`, `failed`, con el motivo en `runs.error`. Si no, queda en `running`.
- **Los totales salen de los pasos**: al cerrar se suman tokens y costo en la base, y también
  mide la latencia total. Un run fallido conserva lo que alcanzó a gastar.
- **Un run cerrado no cambia**: escribir en él, o en un id inexistente, lanza `RunNotRunningError`.
- **Un paso tiene `output` o `error`, nunca ambos ni ninguno**, y un `llm_call` exige `model_id`.
- **Los pasos de un run se agregan de a uno.** Dos `add_step` simultáneos sobre el mismo run pueden
  chocar por la posición, y uno falla con error de la base.

### Consultar trazas y métricas

```bash
curl -u demo:$API_ACCESS_PASSWORD "localhost:8000/runs?agent_id=<id>&limit=20"
curl -u demo:$API_ACCESS_PASSWORD localhost:8000/agents/<id>/metrics
curl -u demo:$API_ACCESS_PASSWORD "localhost:8000/agents/<id>/metrics?origin=production"
```

| Endpoint | Qué devuelve |
|---|---|
| `GET /runs` | Los runs más recientes con sus pasos. `agent_id` es opcional; `limit` va de 1 a 200 (50 por defecto). |
| `GET /agents/{id}/metrics` | `total_runs`, `total_cost`, `latency_p50_ms` y `error_rate` (de 0 a 1). Responde 404 si el agente no existe. |

Por defecto, las métricas incluyen runs de todos los orígenes, también evals y playground; con
`origin` (`playground`, `eval`, `builder` o `production`) cuentan solo los de ese origen. El p50 y la tasa de
error solo consideran runs terminados, y son `null` si todavía no hay ninguno. Los importes llegan
como strings decimales; un cero puede verse como `0E-8`.

### Pruebas de esta fase

Las consultas usan funciones de Postgres, así que las del recorder y el repositorio solo corren con
`INTEGRATION_DATABASE_URL`, y por lo tanto no corren en CI. La base necesita la extensión `vector`.
Todo se revierte al final y no deja filas:

```bash
INTEGRATION_DATABASE_URL="<connection string>" uv run pytest tests/tracing
```

Para no usar Supabase, sirve una base desechable:

```bash
docker run -d --rm --name bia-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=bia_test \
  -p 55432:5432 pgvector/pgvector:pg17
docker exec bia-pg psql -U postgres -d bia_test -c 'CREATE EXTENSION vector'
INTEGRATION_DATABASE_URL="postgresql://postgres:test@localhost:55432/bia_test" uv run pytest
docker rm -f bia-pg
```

---

## Guía: fase 5 — Runtime de agentes

### Migración obligatoria en bases existentes

Esta fase agrega la columna `runs.error`, y la migración no altera tablas que ya existen. Antes de
desplegar, corre esto en el SQL editor de cada base ya migrada, o fallarán las escrituras y lecturas
de runs:

```sql
ALTER TABLE runs ADD COLUMN IF NOT EXISTS error text;
```

### Ejecutar un agente

```bash
curl -u demo:$API_ACCESS_PASSWORD -X POST localhost:8000/agents/<id>/run \
  -H 'Content-Type: application/json' -d '{"input": "¿Cuál es el saldo del cliente 100001?"}'
```

| Respuesta | Cuándo |
|---|---|
| 200, `status: succeeded` | Hay respuesta en `output`. |
| 200, `status: failed` | El run se ejecutó pero falló, con el motivo en `error`: falló el proveedor o se llegó al tope de iteraciones. |
| 404 | El agente no existe o no tiene versión activa. |
| 409 | La spec apunta a un modelo inexistente, o a una herramienta inexistente o retirada. No se gasta ningún token. |
| 500 | Un error inesperado. El run queda cerrado como `failed`, salvo que la base sea lo que falló. |

Toda respuesta 200 trae `run_id`; la traza se consulta en `GET /runs?agent_id=<id>`.

### Forma de la spec

Para crear un agente que ejecutar, ver la guía de la fase 6. La spec es un JSON con la forma de
`AgentSpec` ([artifacts.py](backend/bia/agents/artifacts.py)):

```json
{
  "purpose": "Responder dudas de facturación",
  "system_prompt": "Eres el asistente de facturación de Bia.",
  "model_id": "<id de GET /models>",
  "tool_names": ["consultar_factura"],
  "guardrails": ["No inventes saldos."],
  "max_iterations": 5
}
```

- `guardrails` se agregan como lista al final del system prompt, así que escríbelos como instrucciones.
- `max_iterations` va de 1 a 20. Cada iteración es una llamada al modelo.
- Un campo desconocido invalida la spec. No hay `temperature`, porque los modelos sembrados no la
  aceptan.
- `knowledge_base_id` es la única base que puede leer `buscar_conocimiento` (ver fase 7).

### Cómo se comporta el loop

- **Errores de herramienta**: JSON inválido, argumentos que no cumplen el schema, una herramienta no
  asignada al agente o un error de la propia herramienta vuelven al modelo como mensaje, para que
  pueda corregir. El paso queda con `error` y el run sigue.
- **Caídas de una herramienta**: el modelo y la traza reciben un mensaje genérico, para no exponer
  detalles internos. El detalle queda en los logs.
- **Fallos del proveedor**: quedan como paso con `error` y terminan el run como `failed`.
- **Conexiones**: las lecturas usan una transacción corta y cada traza la suya, para no retener una
  conexión del pooler durante las llamadas al modelo.

### Probar código que ejecuta agentes

`FakeRunRecorder` ([fake.py](backend/tests/tracing/fake.py)) reemplaza la base, y junto con
`FakeModelProvider` permite probar el loop en cada `uv run pytest`, también en CI. La carga desde la
base y la traza completa en SQL real están en
[test_execution.py](backend/tests/runtime/test_execution.py), y requieren `INTEGRATION_DATABASE_URL`.

---

## Guía: fase 6 — Registro de agentes

No hay migración nueva: esta fase usa las tablas `agents` y `agent_versions` que ya existían. La base
sí necesita un modelo de embeddings activo en el catálogo; el seed ya trae uno.

### Crear un agente

```bash
curl -u demo:$API_ACCESS_PASSWORD -X POST localhost:8000/agents \
  -H 'Content-Type: application/json' -d '{
    "name": "Asistente de facturación",
    "description": "Responde dudas de clientes sobre sus facturas",
    "owner_area": "Servicio al cliente",
    "creator": "Ana",
    "spec": {
      "purpose": "Responder dudas de facturación",
      "system_prompt": "Eres el asistente de facturación de Bia.",
      "model_id": "<id de GET /models?only_active=true>",
      "tool_names": ["consultar_factura"]
    }
  }'
```

El agente queda como `user`, en `draft` y en la versión 1. Ya se puede ejecutar con
`POST /agents/{id}/run`. Antes de crearlo se valida la spec, y después se genera el embedding de la
descripción. Si algo falla, no queda nada creado.

El embedding se registra como un run de origen `builder`. Por eso un agente nuevo ya tiene un run y
su costo en `GET /agents/{id}/metrics`; usa `?origin=playground` para ver solo otros orígenes.

### Editar un agente y volver atrás

```bash
curl -u demo:$API_ACCESS_PASSWORD -X PATCH localhost:8000/agents/<id> \
  -H 'Content-Type: application/json' -d '{"guardrails": ["No inventes saldos."]}'
curl -u demo:$API_ACCESS_PASSWORD localhost:8000/agents/<id>/versions
curl -u demo:$API_ACCESS_PASSWORD -X POST localhost:8000/agents/<id>/versions/1/activate
```

- `PATCH` recibe solo los campos de la spec que cambian y crea una versión nueva, que queda activa.
  Las versiones anteriores nunca se modifican.
- Después de volver a una versión anterior, el siguiente `PATCH` parte de esa versión y toma el número
  siguiente de la secuencia.
- `"knowledge_base_id": null` quita la base de conocimiento. En los demás campos, `null` no es válido.

| Endpoint | Respuestas de error |
|---|---|
| `GET /agents` | Ninguna. Lista los agentes, del más nuevo al más viejo. |
| `GET /agents/{id}` | 404: el agente no existe. |
| `POST /agents` | 422: spec inválida. 502: falló el embedding. 503: no hay modelo de embeddings activo. |
| `PATCH /agents/{id}` | 404: el agente no existe o no tiene versión activa. 422: spec inválida o sin cambios. |
| `GET /agents/{id}/versions` | 404: el agente no existe. |
| `POST /agents/{id}/versions/{n}/activate` | 404: no existe el agente o la versión. 409: la versión usa una herramienta retirada. |

### Qué valida el catálogo

| Referencia de la spec | Versión nueva (`POST`, `PATCH`) | Volver atrás (`activate`) |
|---|---|---|
| Modelo inexistente | Rechazado | Permitido, y el run responde 409 |
| Modelo retirado | Rechazado | Permitido: el runtime lo sigue ejecutando |
| Modelo de embeddings | Rechazado | Permitido, y el run queda `failed` |
| Herramienta inexistente o retirada | Rechazada | Rechazada: el runtime no la ejecutaría |
| Base de conocimiento inexistente, o sin su herramienta (ver fase 7) | Rechazada | Permitida |

El error enumera todos los problemas de una vez. Como cada `PATCH` valida la spec completa, un agente
cuyo modelo fue retirado no acepta ediciones hasta que el mismo `PATCH` elija otro modelo.

### Limitaciones actuales

- **Ningún endpoint cambia el estado.** Todos los agentes quedan en `draft`; publicar llega en la fase 9.
- **`PATCH` solo edita la spec.** El nombre, la descripción, el área y el creador no se pueden cambiar.
- **`designer_justification` queda nulo** y `kind` siempre es `user`; el Builder los usará en la fase 8.
- **Si falla la escritura de la traza** después de crear el agente, la respuesta es 500 pero el agente
  ya existe. Reintentar crearía otro.

### Pruebas de esta fase

La validación y los routers corren en cada `uv run pytest`, también en CI. El registro y su SQL usan
Postgres, así que requieren `INTEGRATION_DATABASE_URL` (ver la base desechable en la fase 4):

```bash
INTEGRATION_DATABASE_URL="<connection string>" uv run pytest tests/agents
```

---

## Guía: fase 7 — RAG

No hay migración nueva: esta fase usa las tablas `knowledge_*` que ya existían. Al arrancar, la API
registra sola la herramienta `buscar_conocimiento`. La base necesita un modelo de embeddings activo.

### Cargar conocimiento

Los documentos de la demo, ficticios, están en [data/knowledge/](data/knowledge/). La API recibe el
texto en el cuerpo porque el backend desplegado no tiene acceso a los archivos del repo. Desde la
raíz del repo, con la API corriendo:

```bash
BASE=$(curl -s -u demo:$API_ACCESS_PASSWORD -X POST localhost:8000/knowledge-bases \
  -H 'Content-Type: application/json' \
  -d '{"name": "Facturación", "description": "Tarifas, procedimientos y FAQ"}' | jq -r .id)

jq -n --rawfile content data/knowledge/tarifas.md \
  '{title: "Tarifas de energía 2026", document_type: "tariff", content: $content}' \
  | curl -u demo:$API_ACCESS_PASSWORD -X POST localhost:8000/knowledge-bases/$BASE/ingest \
    -H 'Content-Type: application/json' -d @-
```

Repite el segundo comando con `procedimientos-facturacion.md` (`procedure`) y
`preguntas-frecuentes.md` (`faq`). También se aceptan `valid_from` y `valid_until` (`YYYY-MM-DD`).

- **Reingerir es seguro:** el documento se identifica por su título dentro de la base, y sus chunks se
  reemplazan completos. Si falla el embedding, la versión anterior queda intacta.
- **Cambiar el título crea otro documento.** Todavía no hay forma de borrar uno por la API.

### Cómo se divide cada tipo de documento

| Tipo | Un chunk por | Sección que se cita |
|---|---|---|
| `tariff`, `procedure` | Cada encabezado con texto; las tablas y los pasos no se parten | La ruta de encabezados: `Tarifas > Tarifa residencial` |
| `faq` | Cada encabezado terminado en `?`, con su respuesta | La pregunta |

En una FAQ, los demás encabezados solo agrupan: texto debajo de ellos o una pregunta sin respuesta
rechazan el documento, para no perder contenido en silencio. Tampoco se acepta una sección de más de
8.000 caracteres ni un documento de más de 200.000: divídelos. El divisor no reconoce bloques de código,
así que una línea que empiece con `#` dentro de uno cuenta como encabezado.

### Buscar

```bash
curl -u demo:$API_ACCESS_PASSWORD -G localhost:8000/knowledge-bases/$BASE/search \
  --data-urlencode 'q=¿Cuánto cuesta el kWh en estrato 2?' --data top_k=3
```

Devuelve los chunks más cercanos primero, con `document`, `section`, `content` y `similarity`.
`top_k` va de 1 a 20 (5 por defecto). Solo cuentan los documentos vigentes hoy, con ambas fechas
inclusive y según la fecha de la base de datos.

| Endpoint | Respuestas de error |
|---|---|
| `POST /knowledge-bases` | 422: cuerpo inválido. |
| `POST /knowledge-bases/{id}/ingest` | 404: la base no existe. 422: documento inválido. 502: falló el embedding. 503: no hay modelo de embeddings activo. |
| `GET /knowledge-bases/{id}/search` | 404: la base no existe. 422: parámetros inválidos. 502: falló el embedding. 503: no hay modelo de embeddings activo. |

### Darle conocimiento a un agente

La spec necesita las dos cosas juntas; si falta una, o la base no existe, se rechaza con 422:

```json
{
  "tool_names": ["buscar_conocimiento"],
  "knowledge_base_id": "<id de la base>"
}
```

El modelo solo envía la pregunta. La base sale de la spec, así que un agente no puede leer otra. Un
agente que ya tenía `knowledge_base_id` sin la herramienta no acepta ediciones hasta que el `PATCH`
agregue la herramienta o quite la base.

Indica en el system prompt que responda solo con lo recuperado y que cite documento y sección. La
búsqueda no tiene umbral de similitud: una pregunta fuera de tema igual devuelve fragmentos, con una
similitud baja (0,1 en la prueba con "la capital de Francia", contra 0,65-0,85 en preguntas de
facturación), y es el modelo el que debe descartarlos.

### Qué queda en la traza

Cada búsqueda de un agente es un único paso `retrieval` en `GET /runs`: con `tool_id`, el `model_id` de
embeddings, sus tokens y su costo, y los chunks devueltos en `output`. Ese costo se suma al del run. Si
la búsqueda falla, el modelo recibe un mensaje genérico, el paso queda con `error` y el run sigue. El
detalle queda en los logs.

### Limitaciones actuales

- **La ingesta y la búsqueda directa no quedan en `runs`**, porque un run exige un agente. Su modelo,
  tokens, costo y latencia vuelven en la respuesta, y la ingesta también los escribe en los logs. Por eso
  no aparecen en las métricas ni en los inventarios.
- **Reingerir siempre genera los embeddings de nuevo**, aunque el texto no haya cambiado.
- **`POST /knowledge-bases` no evita nombres repetidos**, y no hay endpoints para listar bases.
- **La búsqueda recorre todos los chunks de la base**, porque no hay índice vectorial. Basta para unos
  pocos documentos; una base grande necesitará uno.

### Pruebas de esta fase

La división, los contratos, la herramienta y los routers corren en cada `uv run pytest`, también en CI.
La ingesta, la búsqueda y la ejecución con recuperación usan pgvector, así que requieren
`INTEGRATION_DATABASE_URL` (ver la base desechable en la fase 4):

```bash
INTEGRATION_DATABASE_URL="<connection string>" uv run pytest tests/rag tests/runtime
```
