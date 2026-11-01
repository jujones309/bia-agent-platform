# Modelo de datos — Bia Agent Platform

Fuente de verdad de las columnas: cada `bia/database/queries/<tabla>/table.sql` documenta
sus columnas a partir de este archivo. Si una columna cambia, se cambia primero aquí.

## Convenciones

- Todas las tablas viven en el esquema `public`, con clave primaria `id uuid` generada por
  `gen_random_uuid()`, salvo que se indique otra cosa.
- Los costos se guardan en dólares (USD). Los tokens son conteos enteros.
- Row Level Security está activo en todas las tablas y sin políticas: Supabase publica el
  esquema `public` por su API de datos, y así nadie entra por ahí. El backend se conecta con
  el rol dueño de las tablas, al que RLS no aplica.
- `CHECK` solo fija los valores que el plan ya acordó (marcados como **cerrado**). Los
  valores **propuestos** se validan con enums en Python cuando se implemente su fase.
- No se crean índices explícitos. Las restricciones `UNIQUE` existen por integridad, aunque
  Postgres las respalde internamente con un índice.

## Orden de dependencias

`models` → `tools` → `agents` → `agent_versions` → `knowledge_bases` → `knowledge_documents`
→ `knowledge_chunks` → `runs` → `run_steps` → `eval_cases` → `eval_results` →
`orchestrations` → `orchestration_steps`

## Catálogos

### `models`

Catálogo curado de modelos que un agente puede usar. Único por `(provider, provider_model_id)`.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del modelo en el catálogo; lo que referencia una spec. |
| `name` | `text` | Nombre legible para los inventarios. |
| `provider` | `text` | Proveedor que lo sirve. Propuesto: `openai`. |
| `provider_model_id` | `text` | Identificador exacto que espera la API del proveedor. |
| `size` | `text` | Categoría para elegir modelo. Cerrado: `large`, `small`, `embedding`. |
| `input_cost_per_million` | `numeric(12,6)` | USD por 1M de tokens de entrada. |
| `output_cost_per_million` | `numeric(12,6)` | USD por 1M de tokens de salida; 0 en embeddings. |
| `context_window` | `integer` | Máximo de tokens que acepta en una llamada. |
| `recommended_use` | `text` | Cuándo conviene usarlo; lo lee el diseñador al justificar su elección. |
| `is_active` | `boolean` | Si puede elegirse para agentes nuevos. |
| `created_at` | `timestamptz` | Cuándo entró al catálogo. |

### `tools`

Catálogo curado de herramientas, sincronizado desde el registry en código (tarea 3.5). `name`
es único.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador de la herramienta. |
| `name` | `text` | Nombre con el que el modelo la invoca y la spec la referencia. |
| `description` | `text` | Qué hace; el modelo y el diseñador deciden con este texto. |
| `parameters_schema` | `jsonb` | JSON Schema de los argumentos. |
| `risk_level` | `text` | Qué tan delicado es su efecto. Propuesto: `low`, `medium`, `high`. |
| `is_active` | `boolean` | Si puede asignarse a agentes. |
| `created_at` | `timestamptz` | Cuándo entró al catálogo. |

## Agentes

### `agents`

Identidad estable de un agente; su configuración vive en `agent_versions`.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del agente. |
| `name` | `text` | Nombre visible en los inventarios. |
| `description` | `text` | Qué necesidad cubre; es el texto que compara la detección de duplicados. |
| `owner_area` | `text` | Área de Bia responsable del agente. |
| `creator` | `text` | Persona que lo creó. |
| `status` | `text` | Ciclo de vida. Cerrado: `draft`, `testing`, `published`, `archived`. |
| `kind` | `text` | Cerrado: `user` (creado por empleados), `system` (partes de la plataforma). |
| `description_embedding` | `vector(1536)` | Embedding de `description` para buscar duplicados; nulo hasta generarlo. |
| `active_version_number` | `integer` | Número de la versión vigente; nulo antes de la primera. Es un número y no una FK para evitar un ciclo entre `agents` y `agent_versions`. |
| `created_at` | `timestamptz` | Cuándo se registró. |
| `updated_at` | `timestamptz` | Última modificación del registro. |

### `agent_versions`

Versiones inmutables de la spec. Único por `(agent_id, version_number)`.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador de la versión. |
| `agent_id` | `uuid` → `agents` | Agente al que pertenece. |
| `version_number` | `integer` | Consecutivo dentro del agente, desde 1. |
| `spec` | `jsonb` | Spec declarativa que ejecuta el runtime. |
| `designer_justification` | `text` | Por qué el diseñador propuso esta spec; nulo si la versión fue manual. |
| `created_at` | `timestamptz` | Cuándo se creó la versión. |

## Conocimiento

### `knowledge_bases`

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador de la base; lo que referencia una spec. |
| `name` | `text` | Nombre visible, por ejemplo "Facturación". |
| `description` | `text` | Qué conocimiento contiene. |
| `created_at` | `timestamptz` | Cuándo se creó. |

### `knowledge_documents`

Único por `(knowledge_base_id, title)`, lo que hace idempotente la ingesta por documento.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del documento. |
| `knowledge_base_id` | `uuid` → `knowledge_bases` | Base a la que pertenece. |
| `title` | `text` | Título; es la fuente que cita el agente. |
| `document_type` | `text` | Define la estrategia de chunking. Cerrado: `tariff`, `procedure`, `faq`. |
| `valid_from` | `date` | Desde cuándo rige el contenido; nulo si no aplica. |
| `valid_until` | `date` | Hasta cuándo rige; nulo si sigue vigente. |
| `created_at` | `timestamptz` | Cuándo se ingirió. |

### `knowledge_chunks`

Se borran en cascada con su documento, para poder reingerirlo.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del fragmento. |
| `document_id` | `uuid` → `knowledge_documents` | Documento de origen. |
| `content` | `text` | Texto recuperado y entregado al agente. |
| `metadata` | `jsonb` | Datos para citar, como la sección y el documento. |
| `embedding` | `vector(1536)` | Embedding de `content` para la búsqueda semántica. |
| `created_at` | `timestamptz` | Cuándo se generó. |

## Trazas

### `runs`

Una ejecución completa de un agente.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del run. |
| `agent_id` | `uuid` → `agents` | Agente ejecutado. |
| `agent_version_id` | `uuid` → `agent_versions` | Versión exacta ejecutada. |
| `origin` | `text` | Quién lo disparó. Propuesto: `playground`, `eval`, `builder`, `production`. |
| `input` | `text` | Entrada recibida. |
| `output` | `text` | Respuesta final; nula mientras corre o si falló. |
| `status` | `text` | Estado. Propuesto: `running`, `succeeded`, `failed`. |
| `total_tokens` | `integer` | Suma de los tokens de sus pasos. |
| `total_cost` | `numeric(14,8)` | Suma en USD del costo de sus pasos. |
| `latency_ms` | `integer` | Duración total; nula hasta terminar. |
| `started_at` | `timestamptz` | Cuándo empezó. |
| `finished_at` | `timestamptz` | Cuándo terminó; nulo mientras corre. |

### `run_steps`

Un paso dentro de un run. Único por `(run_id, step_order)`.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del paso. |
| `run_id` | `uuid` → `runs` | Run al que pertenece. |
| `step_order` | `integer` | Posición dentro del run, desde 1. |
| `step_type` | `text` | Cerrado: `llm_call`, `tool_call`, `retrieval`. |
| `model_id` | `uuid` → `models` | Modelo usado; nulo si el paso no llamó a un modelo. |
| `tool_id` | `uuid` → `tools` | Herramienta usada; nula si el paso no llamó a una. |
| `input` | `jsonb` | Lo que recibió el paso. |
| `output` | `jsonb` | Lo que devolvió; nulo si falló. |
| `input_tokens` | `integer` | Tokens de entrada; 0 si no llamó a un modelo. |
| `output_tokens` | `integer` | Tokens de salida; 0 si no llamó a un modelo. |
| `cost` | `numeric(14,8)` | Costo del paso en USD. |
| `latency_ms` | `integer` | Duración del paso. |
| `error` | `text` | Mensaje de error; nulo si salió bien. |
| `created_at` | `timestamptz` | Cuándo se registró. |

## Evals

### `eval_cases`

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del caso. |
| `agent_id` | `uuid` → `agents` | Agente que evalúa. |
| `input` | `text` | Mensaje de prueba. |
| `expected_behavior` | `text` | Qué debería hacer el agente; contra esto compara el juez. |
| `origin` | `text` | Cerrado: `generated`, `manual`. |
| `created_at` | `timestamptz` | Cuándo se creó. |

### `eval_results`

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del resultado. |
| `eval_case_id` | `uuid` → `eval_cases` | Caso evaluado. |
| `agent_version_id` | `uuid` → `agent_versions` | Versión evaluada. |
| `output` | `text` | Respuesta del agente. |
| `verdict` | `text` | Decisión del juez. Propuesto: `pass`, `fail`. |
| `score` | `numeric(5,2)` | Puntaje del juez, de 0 a 100; alimenta el gate de publicación. |
| `judge_reason` | `text` | Por qué el juez decidió así. |
| `created_at` | `timestamptz` | Cuándo se evaluó. |

## Orquestación

### `orchestrations`

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del flujo. |
| `name` | `text` | Nombre visible en el inventario. |
| `description` | `text` | Qué logra el flujo. |
| `orchestration_type` | `text` | Forma del flujo. Propuesto: `single_agent`, `sequential`. |
| `created_at` | `timestamptz` | Cuándo se registró. |

### `orchestration_steps`

Único por `(orchestration_id, step_order)`.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid` | Identificador del paso. |
| `orchestration_id` | `uuid` → `orchestrations` | Flujo al que pertenece. |
| `step_order` | `integer` | Posición dentro del flujo, desde 1. |
| `agent_id` | `uuid` → `agents` | Agente que ejecuta el paso. |
| `receives_context` | `text` | Qué contexto recibe. |
| `delivers_output` | `text` | Qué entrega al paso siguiente. |
