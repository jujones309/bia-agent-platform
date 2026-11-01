# Guion del video de la demo

Duración objetivo: unos 4 min 30 s. Resuelve la tarea 14.3 de [PLAN.md](PLAN.md).

## Antes de grabar

- **Usa una base nueva y migrada.** En la base de `.env`, `check` ya responde `exists` para la descripción original, y
  no hay forma de borrar agentes (ver la guía de la fase 10 del [README](../README.md)).
- **Crea la base de conocimiento "Facturación" antes de grabar** e ingiere los 3 documentos (ver la guía de la fase 7). Sin
  ella, el diseñador propone el agente sin base.
- **Apunta el backend a esa base** con `DATABASE_URL`. Para que el flujo de facturación salga en `/orchestrations`, corre
  `uv run python -m bia.orchestrations.flows --billing-agent-id <id>` después de publicar y antes de grabar esa toma.
- **Prepara el diagrama:** deja abierto el de la sección 1 de [ARCHITECTURE.md](ARCHITECTURE.md), ya renderizado.
- **Abre una sesión en el frontend** y deja el texto de cada descripción a mano.
- **Costo y espera:** el flujo costó unos USD 0,03 en las pruebas. Generar casos y correr evals tarda de 1 a 4 minutos, así
  que **corta esa espera al editar**.

Las respuestas del modelo pueden variar. Si una toma sale distinta, narra lo que se ve, no lo que dice este guion.

## Guion

| Tiempo | En pantalla | Qué decir |
|---|---|---|
| 0:00-0:30 | Título o `/agents` | "Sin una plataforma común, cada área que quiere un agente de IA arranca de cero, y nadie ve qué existe, qué modelos usa ni cuánto cuesta. Esta plataforma permite que cualquier persona de Bia cree un agente sobre un catálogo curado, y deja registrado todo lo que hace." |
| 0:30-1:10 | Diagrama de arquitectura | "La decisión central: un agente no es código, es una spec versionada en la base de datos. Un único runtime la ejecuta. Por eso ningún agente puede saltarse el catálogo ni las trazas. Alrededor están el Builder, que crea agentes; RAG, para el conocimiento; los evals, que deciden qué se publica; y una sola puerta hacia los modelos." |
| 1:10-1:35 | `/builder`: pegar la descripción y chequear | "Describo lo que necesito, sin escribir un prompt: un asistente para servicio al cliente que responda dudas de facturación, con saldo, tarifas y reclamos. Primero busca si ya existe. Aquí responde que no." |
| 1:35-2:10 | Proponer y revisar la spec | "El diseñador propone el agente. Solo puede elegir del catálogo, y si inventa un modelo, la validación lo rechaza. Eligió el modelo pequeño, y aquí explica por qué: es la justificación de cada decisión. Yo reviso, y puedo ajustar lo que quiera." |
| 2:10-2:45 | Generar casos, correr evals (espera cortada), publicar | "Antes de publicar, se generan casos de prueba, incluso fuera de alcance. Se ejecutan con el runtime real y un juez los califica. El botón de publicar estaba deshabilitado: hace falta 80 % como mínimo. Pasó, así que lo publico." |
| 2:45-3:10 | `/builder`: "Un bot que responda dudas de facturas" | "Ahora otra persona pide casi lo mismo con otras palabras. La plataforma detecta que ya existe y lo ofrece, en vez de crear un duplicado. Esto evita que cada área construya el suyo." |
| 3:10-3:50 | Playground: saldo del cliente 100002 y luego un restaurante; abrir la traza | "Le pregunto por el saldo de un cliente. Como es un dato transaccional, usa una herramienta, no RAG. Cada respuesta enlaza a su traza: aquí están los pasos, con modelo, tokens, costo y latencia. Y si pregunto algo fuera de alcance, lo rechaza." |
| 3:50-4:15 | `/agents`, `/models`, `/orchestrations` | "Y esta es la vista que hoy no existe: qué agentes hay, qué usan y cuánto cuestan. Hasta el propio Builder aparece aquí, porque también está hecho de agentes." |
| 4:15-4:30 | ARCHITECTURE.md o el README | "Una pregunta costó cerca de tres centésimas de centavo de dólar. Lo que falta para producción, como SSO y un canal real, y el plan por fases, está en el documento de arquitectura. Gracias." |

## Después de grabar

1. Sube el video y agrega el enlace a la sección "Entrega" del [README](../README.md).
2. Marca la tarea 14.4 en [PLAN.md](PLAN.md).
