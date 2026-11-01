# MEJORAS.md — Bia Agent Platform

Mejoras pendientes al 2026-11-01. El MVP de [PLAN.md](PLAN.md) está construido: de la fase 14 solo quedan grabar el video y enviar
las invitaciones. Las demás tareas van más allá de ese plan y salen de las limitaciones registradas en el [README](../README.md) y
de la prueba del agente `Resumen de reuniones` en producción.

Marca cada tarea con `[x]` al terminarla y haz un commit por tarea o grupo pequeño (Conventional Commits, ver `CLAUDE.md`). Al cerrar
cada bloque, actualiza el `README.md` con lo construido.

## Resumen de bloques

| Bloque | Tema | Tareas |
|---|---|---|
| 1 | Entrega | 5 |
| 2 | Uso con empleados | 6 |
| 3 | Administración | 8 |
| 4 | Producto | 6 |

**Orden recomendado:** 1 → 2 → 3 → 4. El bloque 2 es requisito para abrir la plataforma a toda la empresa.

---

## Bloque 1 — Entrega

Objetivo: cerrar lo que falta del plan original, con la documentación al día.

- [ ] **1.1 Estado del README** — El párrafo de `## Estado` dice que el frontend no está desplegado, y ya lo está. Corregirlo. *Listo cuando:* el texto coincide con la tabla de `## Entrega`.
- [ ] **1.2 Stack en `CLAUDE.md`** — Nombra Railway como destino del backend, que está en Vercel. Corregir el stack y la configuración. *Listo cuando:* ya no menciona Railway como despliegue actual.
- [ ] **1.3 Base para grabar el Builder** — `check` ya responde `exists` para facturación en esta base. Elegir otra descripción o preparar una base nueva y migrada. *Listo cuando:* el flujo de `check` a publicar se puede grabar sin crear un duplicado.
- [ ] **1.4 Grabar video** — Grabarlo con el [guion](VIDEO_SCRIPT.md), subirlo y enlazarlo en el README (tarea 14.4 del plan).
- [ ] **1.5 Invitaciones** — Quien administra el repo debe invitar a las personas indicadas en el plan (tarea 14.5). *Listo cuando:* aparecen como pendientes en GitHub.

## Bloque 2 — Uso con empleados

Objetivo: saber quién hace qué, separar la producción de las pruebas y proteger lo que se guarda.

- [ ] **2.1 Identidad por persona** — Reemplazar la contraseña compartida, con la que no se sabe quién hizo qué, por un acceso individual. *Listo cuando:* cada petición se asocia a una persona.
- [ ] **2.2 Permisos por rol** — Definir quién puede crear, editar, publicar y consultar trazas. *Listo cuando:* una acción sin permiso se rechaza con un error claro.
- [ ] **2.3 Creador desde la sesión** — `creator` es texto libre; tomarlo de la persona autenticada. *Listo cuando:* no se puede registrar otro nombre.
- [ ] **2.4 Canal de producción** — Hoy ningún endpoint crea runs de origen `production` y el runtime ejecuta agentes en cualquier estado. Crear un canal que exija `published` y registre sus runs como `production`. *Listo cuando:* un agente sin publicar se rechaza y el monitoreo de deriva tiene runs que revisar.
- [ ] **2.5 Datos sensibles en las trazas** — Las entradas se guardan completas en `runs.input`, sin enmascarar. Definir qué se guarda, por cuánto tiempo y quién puede leerlo, y aplicarlo. *Listo cuando:* la política está documentada y se cumple en el código.
- [ ] **2.6 Evals en segundo plano** — Cada corrida es una sola petición síncrona. Los 12 casos de facturación tardaron 3 min 31 s en local y no se han probado en Vercel; solo pasaron 12 casos sin herramientas, en 58 s. Ejecutarlas como trabajo en segundo plano, con progreso consultable. *Listo cuando:* la corrida de facturación termina en el despliegue.

## Bloque 3 — Administración

Objetivo: que quienes crean agentes los gestionen desde la interfaz, sin API ni SQL.

- [x] **3.1 Archivar agentes** — El estado `archived` existe, pero no hay endpoint para llegar a él. Agregar endpoint y botón. *Listo cuando:* un agente archivado sale de la búsqueda de duplicados y conserva sus trazas.
- [x] **3.2 Borrar casos, documentos y flujos** — Un caso mal generado solo se quita con SQL a mano, y los documentos y flujos no se pueden borrar. Agregar endpoints y pantallas que conserven el historial de auditoría. *Listo cuando:* cada recurso se retira sin SQL.
- [x] **3.3 Casos manuales en la interfaz** — Solo se agregan por API, y el generador inventa números de cliente, así que desde la interfaz no se cubre una consulta exitosa. Agregar un formulario en la pantalla de evals. *Listo cuando:* un caso nuevo se crea y se corre desde el navegador.
- [x] **3.4 Listar bases de conocimiento** — Ningún endpoint las lista, y por eso el formulario no permite cambiar la base de un agente. Agregar `GET /knowledge-bases` y el selector. *Listo cuando:* se elige la base desde la revisión de la spec.
- [x] **3.5 Crear bases e ingerir en la interfaz** — Hoy solo se puede por API. Agregar pantallas para crear una base y cargar documentos. *Listo cuando:* una persona no técnica deja una base lista para el Builder.
- [x] **3.6 Flujos automáticos** — Los agentes nuevos no aparecen en Orquestación, y no hay endpoint para crear flujos. Registrar el flujo de un solo agente al publicar. *Listo cuando:* un agente recién publicado se ve en `/orchestrations`.
- [x] **3.7 Métricas y versiones en la interfaz** — Los endpoints existen, pero faltan las pantallas de métricas y de vuelta a una versión anterior. *Listo cuando:* ambas acciones se hacen desde el detalle del agente.
- [x] **3.8 Identidad del agente** — `PATCH` solo edita la spec. Permitir cambiar nombre, descripción y área, regenerando el embedding si cambia la descripción. *Listo cuando:* la búsqueda de duplicados encuentra la descripción nueva.

## Bloque 4 — Producto

Objetivo: ampliar lo que pueden hacer los agentes y medir mejor su calidad.

- [ ] **4.1 Más herramientas** — Solo hay dos, ambas de facturación, y eso limita qué agentes puede crear el Builder. Priorizar con las áreas y sumar las primeras al catálogo. Es la mejora con más impacto en el valor de la plataforma. *Listo cuando:* el Builder propone agentes útiles fuera de facturación usando esas herramientas.
- [x] **4.2 Memoria de conversación** — Un run del playground es ahora una conversación completa: guarda memoria y sigue abierto hasta que se finaliza, y el siguiente mensaje abre otro. *Listo cuando:* el playground responde una pregunta de seguimiento. Falta comprobarlo con el modelo real; ver la [guía](../README.md#guía-tarea-42-de-mejoras--memoria-de-conversación).
- [ ] **4.3 Casos escritos por el área dueña** — Los casos generados salen de la misma spec que evalúan, así que miden si el agente la cumple, no si es útil. Incorporar casos de las áreas al flujo de publicación. *Listo cuando:* el proceso de publicación los pide.
- [ ] **4.4 Expectativas exactas en los casos** — El juez no penaliza lo que el caso no prohíbe de forma explícita, como una tarea de más. Ajustar el generador para que escriba expectativas exactas, como "exactamente tres tareas". *Listo cuando:* una respuesta con un elemento de más reprueba en un caso generado.
- [ ] **4.5 Umbral de similitud en RAG** — Una pregunta fuera de tema igual devuelve fragmentos, y es el modelo quien debe descartarlos. Calibrar un umbral con preguntas reales. *Listo cuando:* una pregunta fuera de tema no devuelve fragmentos.
- [ ] **4.6 Índice vectorial** — La búsqueda recorre todos los chunks. Basta con pocos documentos, pero no con una base grande. Agregar un índice cuando el volumen lo justifique. *Listo cuando:* la latencia se mantiene estable con el volumen objetivo.
