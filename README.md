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
| 5-14 | Runtime, Builder, frontend y entrega | Pendientes |

Hoy existen la API con `GET /health`, la protección con contraseña, el esquema de base de datos,
el provider de modelos, los catálogos de modelos y herramientas y el registro de trazas. El Builder
y el runtime todavía no están construidos, así que nada genera runs por sí solo. El detalle está en
[docs/PLAN.md](docs/PLAN.md).

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

`GET_BY_ID` es un ejemplo: todavía no existe. Al salir del bloque se hace commit, y si hay una
excepción se hace rollback y la excepción se propaga.

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

`run(args)` recibe los argumentos ya validados. Esa validación contra el schema llega con el
runtime (tarea 5.4); hasta entonces, un argumento faltante lanza `KeyError`. Los fallos esperados,
como un cliente inexistente, se devuelven como `ToolResult(error=...)` para que el modelo pueda
reaccionar.

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
from bia.catalog.tools.registry import get_tool

get_tool("consultar_factura").run({"numero_cliente": "100001"})
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

Cada ejecución queda en `runs` y cada uno de sus pasos en `run_steps`. El runtime todavía no existe:
hasta la fase 5, los runs solo aparecen si alguien usa `RunRecorder` directamente.

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
- **`finish_run(run_id, None)` marca el run como `failed`**; con un texto, como `succeeded`. Hay que
  llamarlo también cuando la ejecución falla: de lo contrario, el run queda en `running`.
- **Los totales salen de los pasos**: `finish_run` suma tokens y costo en la base, y también
  mide la latencia total. Un run fallido conserva lo que alcanzó a gastar.
- **Un run cerrado no cambia**: escribir en él, o en un id inexistente, lanza `RunNotRunningError`.
- **Un paso tiene `output` o `error`, nunca ambos ni ninguno**, y un `llm_call` exige `model_id`.
- **Los pasos de un run se agregan de a uno.** Dos `add_step` simultáneos sobre el mismo run pueden
  chocar por la posición, y uno falla con error de la base.

### Consultar trazas y métricas

```bash
curl -u demo:$API_ACCESS_PASSWORD "localhost:8000/runs?agent_id=<id>&limit=20"
curl -u demo:$API_ACCESS_PASSWORD localhost:8000/agents/<id>/metrics
```

| Endpoint | Qué devuelve |
|---|---|
| `GET /runs` | Los runs más recientes con sus pasos. `agent_id` es opcional; `limit` va de 1 a 200 (50 por defecto). |
| `GET /agents/{id}/metrics` | `total_runs`, `total_cost`, `latency_p50_ms` y `error_rate` (de 0 a 1). Responde 404 si el agente no existe. |

Las métricas incluyen runs de todos los orígenes, también evals y playground. El p50 y la tasa de
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
