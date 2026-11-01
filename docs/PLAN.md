# PLAN.md — Bia Agent Platform

Plan de desarrollo desde cero, dividido en tareas de 10-15 minutos.
Marca cada tarea con `[x]` al terminarla y haz un commit por tarea o grupo pequeño
(Conventional Commits, ver `CLAUDE.md`).
Al cerrar cada fase, agrega al `README.md` su guía de cómo hacer lo construido y actualiza la
tabla de estado (ver `CLAUDE.md`).

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Alcance MVP | Creación de agentes vía Builder + playground + inventarios + trazas |
| Caso real | Asistente de facturación de servicio al cliente |
| Stack | FastAPI (Vercel, proyecto aparte del frontend) + Supabase (Postgres + pgvector) + OpenAI + Next.js (Vercel, al final) |
| Orquestación | Loop propio de tool-calling, sin frameworks |
| Agente | Spec declarativa versionada en la base; un único runtime genérico la ejecuta |
| Builder | Un request con la descripción → propuesta de spec → el usuario la ajusta con `PATCH` antes de publicar |
| Demo intermedia | Swagger (`/docs`) hasta que exista el frontend |

## Resumen de fases

| Fase | Tema | Tareas | Tiempo aprox. |
|---|---|---|---|
| 0 | Setup y deploy temprano | 9 | 2 h |
| 1 | Modelo de datos y base | 11 | 2.5 h |
| 2 | Provider de modelos | 7 | 1.5 h |
| 3 | Catálogos (modelos y herramientas) | 6 | 1.5 h |
| 4 | Trazas | 5 | 1 h |
| 5 | Runtime de agentes | 7 | 1.5 h |
| 6 | Registro de agentes | 6 | 1.5 h |
| 7 | RAG | 8 | 2 h |
| 8 | Agent Builder | 10 | 2.5 h |
| 9 | Evals y publicación | 7 | 1.5 h |
| 10 | Caso real end-to-end | 5 | 1 h |
| 11 | Inventarios y orquestación | 5 | 1 h |
| 12 | Frontend | 10 | 2.5 h |
| 13 | Documento de arquitectura | 9 | 2 h |
| 14 | Entrega | 5 | 1 h |

**Ruta crítica para una demo mínima:** fases 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 10 → 13 → 14.
Ver **Recortes** al final si el tiempo aprieta.

---

## Fase 0 — Setup y deploy temprano

Objetivo: repo listo, `/health` respondiendo en Railway desde el día uno.

- [x] **0.1 Repo y estructura** — Crear el repo privado, clonar, crear las carpetas de `backend/bia/` y `backend/tests/` según `CLAUDE.md`. Commit de `CLAUDE.md` y `PLAN.md`. *Listo cuando:* el árbol está en GitHub.
- [x] **0.2 Proyecto Python** — `uv init`, dependencias base (`fastapi`, `uvicorn[standard]`, `openai`, `sqlalchemy`, `psycopg[binary]`, `pgvector`, `pydantic-settings`) y dev (`pytest`, `ruff`, `httpx`). *Listo cuando:* `uv sync` corre sin errores.
- [x] **0.3 Settings** — `bia/settings/config.py` con `Settings` (`openai_api_key`, `database_url`, `log_level`, `environment`) y `.env.example`. *Listo cuando:* la app falla con un error claro si falta una variable.
- [x] **0.4 App y logging** — `bia/api/main.py` con la app FastAPI, configuración de logging y `GET /health`. *Listo cuando:* `uv run uvicorn bia.api.main:app --reload` responde en `/health`.
- [x] **0.5 Test de health** — `tests/api/test_main.py` con `TestClient`, que verifica status y body. *Listo cuando:* `uv run pytest` pasa.
- [x] **0.6 Ruff + pytest config** — Configurar ruff (línea, reglas) y pytest en `pyproject.toml` usando los comandos de uv. *Listo cuando:* `uv run ruff check .` queda limpio.
- [x] **0.7 Supabase** — Crear el proyecto y habilitar la extensión `vector`. Copiar la connection string (pooler) a `.env`. *Listo cuando:* conectas con `psql` o desde el SQL editor.
- [x] **0.8 Vercel (backend)** — Importar el repo en vercel.com/new con Root Directory `backend/`, agregar `[tool.vercel] entrypoint = "bia.api.main:app"` en `pyproject.toml` y cargar las variables de entorno. Usar la connection string del *transaction pooler* de Supabase (puerto 6543), porque el entorno es serverless. *Listo cuando:* `/health` responde en la URL pública.
- [x] **0.9 CI mínimo** — GitHub Action que corre `ruff` y `pytest` en cada push. *Listo cuando:* el check sale en verde.

## Fase 1 — Modelo de datos y base

Objetivo: el esquema completo documentado y aplicado en Supabase.

- [x] **1.1 Documento del modelo de datos** — `docs/data-model.md` con cada tabla y cada columna (tipo y significado de negocio). Es la fuente de verdad para los `table.sql`. *Listo cuando:* están las 13 tablas de esta fase.
- [x] **1.2 Conexión** — `bia/database/` con engine y sesión de SQLAlchemy (modo core, sin ORM pesado) y un context manager de sesión. *Listo cuando:* un test de integración hace `SELECT 1`.
- [x] **1.3 Loader de SQL** — `bia/database/queries/load_sql(table, operation)` con test: lee el archivo correcto y falla claro si no existe. *Listo cuando:* el test pasa.
- [x] **1.4 Tablas de catálogo** — `models/table.sql` (nombre, proveedor, id del proveedor, tamaño, costo de entrada/salida por 1M de tokens, ventana de contexto, uso recomendado, activo) y `tools/table.sql` (nombre, descripción, JSON schema de parámetros, nivel de riesgo, activo).
- [x] **1.5 Tablas de agentes** — `agents/table.sql` (nombre, descripción, área dueña, creador, estado, tipo `user`/`system`, embedding de la descripción, versión activa) y `agent_versions/table.sql` (agente, número de versión, spec JSON, justificación del diseñador, fecha).
- [x] **1.6 Tablas de conocimiento** — `knowledge_bases`, `knowledge_documents` (base, título, tipo de documento, vigencia) y `knowledge_chunks` (documento, contenido, metadata, embedding `vector(1536)`).
- [x] **1.7 Tablas de trazas** — `runs` (agente, versión, origen, input, output, estado, tokens totales, costo, latencia) y `run_steps` (run, orden, tipo de paso, modelo, tool, input, output, tokens, costo, latencia, error).
- [x] **1.8 Tablas de evals** — `eval_cases` (agente, input, comportamiento esperado, origen: generado o manual) y `eval_results` (caso, versión, output, veredicto, puntaje, razón del juez).
- [x] **1.9 Tablas de orquestación** — `orchestrations` (nombre, descripción, tipo) y `orchestration_steps` (orquestación, orden, agente, qué contexto recibe y qué entrega). *Listo cuando:* las 13 tablas tienen su `table.sql` documentado.
- [x] **1.10 Script de migración** — `bia/database/migrate.py`, que aplica todos los `table.sql` en orden de dependencias de forma idempotente (`IF NOT EXISTS`). *Listo cuando:* lo corres dos veces contra Supabase sin errores.
- [x] **1.11 Seed del catálogo** — `seed.sql` por tabla con 2-3 modelos de OpenAI (uno grande, uno pequeño, uno de embeddings) y costos reales. *Listo cuando:* los registros se ven en Supabase.

## Fase 2 — Provider de modelos

Objetivo: una sola puerta para hablar con LLMs, con uso y costo medidos.

- [x] **2.1 Contrato** — `bia/providers/artifacts.py` (`ChatMessage`, `ToolCall`, `ChatResult` con `usage` y `latency_ms`, `EmbeddingResult`) y la clase abstracta `ModelProvider` (`chat`, `chat_structured`, `embed`).
- [x] **2.2 Enum de proveedores** — `ProviderName` y una factory `get_provider(provider_name)`. *Listo cuando:* un proveedor desconocido lanza un error claro.
- [x] **2.3 OpenAI: chat** — `bia/providers/openai/` implementa `chat` con soporte de tools y mide latencia. *Listo cuando:* un script manual devuelve respuesta y uso de tokens.
- [x] **2.4 OpenAI: structured output** — `chat_structured(messages, response_model)` que devuelve una instancia pydantic validada.
- [x] **2.5 OpenAI: embeddings** — `embed(texts)` en lote.
- [x] **2.6 Cálculo de costo** — Función pura `compute_cost(usage, catalog_model)` con tests de casos concretos.
- [x] **2.7 Provider falso** — `FakeModelProvider` para tests, con respuestas y tool calls programables. *Listo cuando:* lo usa al menos un test.

## Fase 3 — Catálogos

Objetivo: los inventarios de modelos y herramientas, curados y consultables.

- [x] **3.1 Repositorio de modelos** — Listar, obtener por id y filtrar activos (SQL en `models/`). Los artifacts definen `CatalogModel`.
- [x] **3.2 API de modelos** — `GET /models` y `GET /models/{id}`. *Listo cuando:* se ven en Swagger.
- [x] **3.3 Interfaz de herramienta** — Clase abstracta `Tool` (nombre, descripción, schema de parámetros, `run(args) -> ToolResult`) y un registry que mapea nombre a implementación.
- [x] **3.4 Tool `consultar_factura`** — Datos de facturas falsos (JSON en `bia/catalog/tools/data/`) de ~10 clientes: consulta por número de cliente y devuelve saldo, período, consumo y fecha límite.
- [x] **3.5 Sincronizar tools con la base** — Al arrancar, upsert de las tools del registry a la tabla `tools`. *Listo cuando:* la tabla refleja el código.
- [x] **3.6 API de tools** — `GET /tools`.

## Fase 4 — Trazas

Objetivo: todo lo que hace un agente queda registrado.

- [x] **4.1 Artifacts** — `RunRecord`, `RunStepRecord` y el enum `StepType` (`llm_call`, `tool_call`, `retrieval`).
- [x] **4.2 Recorder** — `RunRecorder`: `start_run`, `add_step` y `finish_run`, que suma tokens y costo de los pasos. Con test usando la base.
- [x] **4.3 API de runs** — `GET /runs?agent_id=`, que devuelve el run con sus pasos.
- [x] **4.4 Métricas por agente** — Query que agrega runs, costo total, latencia p50 y tasa de error por agente.
- [x] **4.5 API de métricas** — `GET /agents/{id}/metrics`.

## Fase 5 — Runtime de agentes

Objetivo: un runtime genérico que ejecuta cualquier spec.

- [x] **5.1 Spec del agente** — `AgentSpec` en `bia/agents/artifacts.py`: propósito, system prompt, `model_id`, `tool_names`, `knowledge_base_id` opcional, guardrails y máximo de iteraciones. Sin temperatura: los modelos sembrados no la aceptan (ver fase 2).
- [x] **5.2 Ensamblado de mensajes** — Construye los mensajes iniciales a partir de la spec y el input del usuario (system prompt + guardrails).
- [x] **5.3 Loop de tool-calling** — Llama al modelo, ejecuta tools y repite hasta obtener respuesta final o llegar al máximo de iteraciones. Respeta el límite de 40 líneas.
- [x] **5.4 Ejecución de tools** — Valida los argumentos contra el schema y convierte los errores de la tool en mensajes al modelo, sin romper el loop.
- [x] **5.5 Integración con trazas** — Cada llamada al LLM y cada tool se registra como paso.
- [x] **5.6 Tests del runtime** — Con el provider falso: respuesta directa, una tool, tool con error y tope de iteraciones.
- [x] **5.7 Endpoint de playground** — `POST /agents/{id}/run` que devuelve la respuesta y el `run_id`.

## Fase 6 — Registro de agentes

Objetivo: inventario de agentes versionado.

- [x] **6.1 Enums** — `AgentStatus` (`draft`, `testing`, `published`, `archived`) y `AgentKind` (`user`, `system`).
- [x] **6.2 Crear agente** — Crea el agente y la versión 1 en `draft`, y genera el embedding de la descripción.
- [x] **6.3 Nueva versión** — Editar la spec crea una versión nueva; nunca se sobrescribe una existente.
- [x] **6.4 Validación contra catálogo** — Un `model_id` o una tool que no existe, o que está inactiva, produce un error claro. Con tests.
- [x] **6.5 API de agentes** — `GET /agents`, `GET /agents/{id}`, `POST /agents`, `PATCH /agents/{id}` (crea una versión) y `GET /agents/{id}/versions`.
- [x] **6.6 Rollback** — `POST /agents/{id}/versions/{n}/activate`.

## Fase 7 — RAG

Objetivo: conocimiento de Bia recuperable con citas.

- [x] **7.1 Documentos de Bia** — Escribir en `data/knowledge/` 3 documentos markdown ficticios pero realistas: tarifas, procedimientos de facturación y FAQ.
- [x] **7.2 Enum de tipo de documento** — `DocumentType` (`tariff`, `procedure`, `faq`), que define la estrategia de chunking.
- [x] **7.3 Chunking** — Por encabezados para procedimientos y tarifas, y por par pregunta-respuesta para la FAQ. Guarda en la metadata la sección y el documento. Con tests.
- [x] **7.4 Ingesta** — Lee, divide, genera embeddings en lote e inserta. Es idempotente por documento.
- [x] **7.5 Búsqueda** — `search_by_embedding.sql` por distancia coseno, filtrada por base de conocimiento, con top-k.
- [x] **7.6 Tool `buscar_conocimiento`** — Devuelve los chunks con su fuente para que el agente cite.
- [x] **7.7 Traza de retrieval** — La búsqueda queda como paso `retrieval` con los chunks devueltos.
- [x] **7.8 API de conocimiento** — `POST /knowledge-bases`, `POST /knowledge-bases/{id}/ingest` y `GET /knowledge-bases/{id}/search?q=`.

## Fase 8 — Agent Builder

Objetivo: de una descripción en lenguaje natural a un agente propuesto, reutilizando antes de crear.

- [x] **8.1 Loader de prompts** — `load_prompt(vertical, name)` que lee los `.md` de `bia/<vertical>/prompts/`.
- [x] **8.2 Artifacts del builder** — `AgentRequest`, `DuplicateVerdict` (enum), `DuplicateCheckResult` (veredicto, agente candidato, razón) y `AgentProposal` (spec + justificación).
- [x] **8.3 Búsqueda de candidatos** — Embedding de la descripción y top-3 de agentes publicados por similitud.
- [x] **8.4 Prompt del juez** — `builder/duplicates/prompts/judge.md`: recibe la necesidad y los candidatos, y devuelve el veredicto estructurado.
- [x] **8.5 Juez** — Combina búsqueda y juez. Si no hay candidatos, devuelve `not_exists` sin llamar al LLM. Con tests usando el provider falso.
- [x] **8.6 Prompt del diseñador** — `builder/designer/prompts/designer.md`: recibe la necesidad, el catálogo de modelos (con costos y uso recomendado), el catálogo de tools y las bases de conocimiento, y devuelve la spec y la justificación de cada decisión.
- [x] **8.7 Diseñador** — Genera la propuesta, la valida contra el catálogo (6.4) y reintenta una vez si es inválida.
- [x] **8.8 Endpoint de chequeo** — `POST /builder/check`, que devuelve el veredicto y el candidato.
- [x] **8.9 Endpoint de propuesta** — `POST /builder/propose`, que crea el agente en `draft` con la spec propuesta. El usuario ajusta luego con `PATCH /agents/{id}`.
- [x] **8.10 Builder como agentes de sistema** — Registrar el juez y el diseñador como agentes `system` y trazar sus llamadas como runs. Así el Builder aparece en sus propios inventarios.

## Fase 9 — Evals y publicación

Objetivo: no se publica nada sin pasar pruebas, y se puede vigilar en producción.

- [ ] **9.1 Generación de casos** — Un prompt genera 8-10 casos (input + comportamiento esperado) a partir de la spec, incluyendo casos fuera de alcance. Se guardan como `generated`.
- [ ] **9.2 Casos manuales** — `POST /agents/{id}/eval-cases` para que el usuario agregue los suyos.
- [ ] **9.3 Juez de evals** — Prompt LLM-as-judge que compara el output con el comportamiento esperado y devuelve veredicto, puntaje y razón.
- [ ] **9.4 Corrida de evals** — Ejecuta todos los casos contra una versión con el runtime real y guarda los resultados.
- [ ] **9.5 Gate de publicación** — `POST /agents/{id}/publish` exige que la versión activa supere un umbral (p. ej. ≥ 80 %). Si no, devuelve el detalle de los casos fallidos. Definir también qué pasa al editar o hacer rollback de un agente `published`: hoy `PATCH` y `activate` cambian la versión activa de inmediato, sin pasar por evals.
- [ ] **9.6 Endpoint de evals** — `POST /agents/{id}/evals/run` y `GET /agents/{id}/evals`.
- [ ] **9.7 Monitoreo en producción** — Endpoint o script que reevalúa una muestra de runs recientes de producción con el juez y reporta deriva. Si no alcanza el tiempo, queda solo documentado.

## Fase 10 — Caso real end-to-end

Objetivo: el asistente de facturación creado a través de la plataforma, tal como se verá en el video.

- [ ] **10.1 Base de conocimiento** — Crear la base "Facturación" e ingerir los 3 documentos.
- [ ] **10.2 Builder** — Desde Swagger, enviar una descripción de servicio al cliente a `check` (debe dar `not_exists`) y luego a `propose`. Revisar la spec propuesta.
- [ ] **10.3 Ajuste y evals** — Ajustar la spec si hace falta, correr evals e iterar hasta pasar el umbral.
- [ ] **10.4 Publicar y probar** — Publicar y lanzar 5 preguntas reales en el playground: saldo de un cliente, explicación de una tarifa, procedimiento de reclamo y una pregunta fuera de alcance.
- [ ] **10.5 Probar duplicados** — Pedir al Builder "un bot que responda dudas de facturas". Debe devolver `exists` con el asistente. *Listo cuando:* el flujo completo queda grabable.

## Fase 11 — Inventarios y orquestación

Objetivo: la vista de conjunto que hoy le falta a Bia.

- [ ] **11.1 Inventario de agentes** — `GET /inventory/agents`: cada agente con área, modelo, tools, base de conocimiento, estado, runs y costo acumulado.
- [ ] **11.2 Inventario de modelos** — `GET /inventory/models`: cada modelo con cuántos agentes lo usan, tokens y costo total.
- [ ] **11.3 Seed de orquestaciones** — Registrar el flujo del Builder (juez → diseñador → generador de casos → juez de evals) y el del asistente de facturación (un agente con dos tools).
- [ ] **11.4 Inventario de orquestación** — `GET /inventory/orchestrations`: cada flujo con sus pasos, agentes y modelos.
- [ ] **11.5 Resumen global** — `GET /inventory/summary`: total de agentes por estado, costo del mes y modelos en uso.

## Fase 12 — Frontend

Objetivo: lo justo para que la demo se vea como producto. Se recorta primero.

- [ ] **12.1 Setup** — Next.js + TypeScript + Tailwind en `frontend/` y deploy vacío a Vercel.
- [ ] **12.2 Cliente de API** — Un módulo único con tipos espejo de los artifacts y la URL del backend por variable de entorno. Configurar CORS en FastAPI.
- [ ] **12.3 Layout** — Sidebar con Agentes, Modelos, Orquestación, Builder y Runs.
- [ ] **12.4 Inventario de agentes** — Tabla con estado, modelo, costo y runs.
- [ ] **12.5 Inventario de modelos y orquestación** — Tablas simples; los pasos de orquestación como lista ordenada.
- [ ] **12.6 Builder: paso 1** — Textarea con la descripción, llamada a `check` y tarjeta "¿Es este agente?" cuando hay candidato.
- [ ] **12.7 Builder: paso 2** — Muestra la spec propuesta en un formulario editable con la justificación del modelo.
- [ ] **12.8 Builder: paso 3** — Corre evals, muestra resultados por caso y habilita el botón de publicar.
- [ ] **12.9 Playground** — Chat contra un agente, con la respuesta y un enlace a su traza.
- [ ] **12.10 Vista de traza** — Pasos del run con tipo, modelo, tokens, costo y latencia.

## Fase 13 — Documento de arquitectura

Objetivo: `docs/ARCHITECTURE.md`, con las 6 preguntas como índice. Ir anotando decisiones desde la fase 0 en `docs/decisions.md` facilita mucho esta fase.

- [ ] **13.1 Diagrama** — Diagrama de arquitectura en Mermaid: builder, runtime, provider, catálogos, RAG, trazas y evals.
- [ ] **13.2 P1: Arquitectura** — Explicación de capas y flujos, y por qué un runtime genérico más specs declarativas.
- [ ] **13.3 P2: ¿Qué es un agente?** — La spec: sus campos, el versionado y el ciclo de vida.
- [ ] **13.4 P3: Usuario sin prompts** — Builder, detección de duplicados, diseñador restringido al catálogo y revisión humana.
- [ ] **13.5 P4: Pruebas y producción** — Evals antes de publicar, gate, trazas, métricas y reevaluación de muestras.
- [ ] **13.6 P5: Caso real** — El asistente de facturación de punta a punta, con números reales de costo y latencia de tus runs.
- [ ] **13.7 P6: Fases y cronograma** — Qué entra en cada fase, qué se compra en vez de construir (Langfuse, LiteLLM, vector DB gestionada) y el riesgo principal de cada paso.
- [ ] **13.8 Temas transversales: modelos y RAG** — Grande vs pequeño, abierto vs cerrado, API vs local, qué hacer cuando sale un modelo mejor (correr evals y cambiar el catálogo). Estructura de documentos y cuándo RAG no es la respuesta (datos transaccionales → tools).
- [ ] **13.9 Temas transversales: fine-tuning y orquestación** — Por qué hoy no se justifica, qué señal lo activaría y con qué datos. Cuándo basta un agente y cuándo dividir en varios, cómo se pasa el contexto y quién decide el flujo.

## Fase 14 — Entrega

- [ ] **14.1 README** — Qué es, cómo correrlo localmente, URLs desplegadas y enlace al documento de arquitectura.
- [ ] **14.2 Revisión de deploy** — Backend en Railway y frontend en Vercel con datos sembrados. Probar el flujo completo en producción.
- [ ] **14.3 Guion del video** — 3-5 minutos: problema, arquitectura (diagrama), Builder creando el asistente, duplicado detectado, playground con traza e inventarios.
- [ ] **14.4 Grabar video** — Grabar y subir. Enlazarlo en el README.
- [ ] **14.5 Invitaciones** — Invitar a `diegogarsfe`, `tatianatorobia` y `juan.otavo@bia.app` (por correo). Verificar que las invitaciones salieron.

---

## Recortes (en orden, si falta tiempo)

1. **Fase 12 reducida** — Solo inventario de agentes, Builder y playground (12.1-12.4, 12.6-12.9). Sin frontend, la demo se hace en Swagger.
2. **9.7** — Monitoreo en producción solo documentado.
3. **6.6** — Rollback solo documentado.
4. **8.10** — Builder como agentes de sistema: documentarlo y sembrar solo la orquestación.
5. **4.4-4.5** — Las métricas por agente se derivan del inventario.
6. **0.9** — Sin CI.

**No recortar nunca:** trazas (fase 4), detección de duplicados (8.3-8.5), validación contra catálogo (6.4) ni el documento (fase 13). Son el corazón del reto.
