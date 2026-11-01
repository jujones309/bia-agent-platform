# Cómo ejecutar Bia Agent Platform

Bia Agent Platform permite crear agentes de IA a partir de una descripción en lenguaje natural, probarlos antes de publicarlos y ver lo que hace cada uno.

Hay dos formas de probarla:

| Opción | Tiempo | Qué necesitas |
|---|---|---|
| [A. Web desplegada](#opción-a-web-desplegada) | 1 minuto | Un navegador y la contraseña de acceso |
| [B. En tu máquina](#opción-b-en-tu-máquina) | 10 a 15 minutos | Docker, uv, Node 24 y una clave de OpenAI |

## Opción A: web desplegada

1. Abre https://bia-agent-platform-frontend.vercel.app.
2. Escribe la contraseña de acceso. No está en el repositorio: la recibes junto con la invitación.
3. Sigue el [recorrido sugerido](#recorrido-sugerido).

Si solo quieres ver la API, abre https://bia-agent-platform.vercel.app/docs. El navegador pide usuario y contraseña: el usuario puede ser cualquiera y la contraseña es la misma.

## Opción B: en tu máquina

### Requisitos

- [Docker](https://www.docker.com/) en ejecución, para la base de datos.
- [uv](https://docs.astral.sh/uv/), para el backend. Instala Python 3.12 si hace falta.
- [Node 24](https://nodejs.org/), para el frontend.
- Una clave de la API de OpenAI con acceso a `gpt-6.1-sol`, `gpt-6-luna` y `text-embedding-3-small`. Crear y evaluar un agente cuesta pocos centavos de dólar.

Los puertos 3000, 5433 y 8000 deben estar libres. Necesitas tres terminales, todas desde la raíz del repositorio.

### 1. Levantar la base de datos

En la primera terminal:

```bash
docker run -d --name bia-db -e POSTGRES_PASSWORD=postgres -p 5433:5432 pgvector/pgvector:pg17
until docker exec bia-db pg_isready -h localhost -U postgres; do sleep 1; done
docker exec bia-db psql -U postgres -c 'CREATE EXTENSION vector'
```

La última línea debe responder `CREATE EXTENSION`.

### 2. Configurar y levantar el backend

En la misma terminal:

```bash
cd backend
uv sync
cp .env.example .env
```

Abre `backend/.env` y deja estos valores:

```bash
OPENAI_API_KEY=<tu clave de OpenAI>
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres
API_ACCESS_PASSWORD=<elige una contraseña de al menos 16 caracteres>
ENVIRONMENT=development
```

Crea las tablas y arranca la API:

```bash
uv run python -m bia.database.migrate
uv run uvicorn bia.api.main:app
```

Para comprobarlo, abre http://localhost:8000/health. Debe responder `{"status":"ok"}`. Deja esta terminal abierta.

### 3. Levantar el frontend

En la segunda terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Deja esta terminal abierta.

### 4. Entrar

Abre http://localhost:3000 y escribe el valor que elegiste para `API_ACCESS_PASSWORD`. Usa exactamente `localhost`: con `127.0.0.1` el navegador bloquea la conexión con el backend.

### 5. Cargar el conocimiento

La base empieza sin documentos, y el agente del recorrido los necesita.

1. Entra a **Conocimiento**.
2. Crea una base con el nombre `Recursos Humanos` y esta descripción: `Políticas internas para empleados: vacaciones, trabajo remoto, incapacidades y licencias`.
3. Abre la base y, en **Cargar un documento**, elige el archivo `data/knowledge/politicas-recursos-humanos.md`.
4. Usa el título `Políticas de recursos humanos` y el tipo **Procedimiento**, y pulsa **Cargar documento**.

## Recorrido sugerido

En la web desplegada ya hay agentes publicados, y la base `Recursos Humanos` puede no existir. Allí, empieza por el paso 5 con `Bia Facturación`, y crea la base como en la [sección anterior](#5-cargar-el-conocimiento) antes de usar el Builder.

1. **Describe la necesidad.** En **Builder**, pega este texto y pulsa **Buscar agentes parecidos**:

   > Un asistente para que los empleados de Bia resuelvan dudas sobre las políticas internas de recursos humanos, como vacaciones, trabajo remoto, incapacidades y licencias, citando el documento de donde sale cada respuesta.

2. **Revisa la propuesta.** Completa **Área dueña** con `Recursos Humanos` y **Quién lo crea** con tu nombre, y pulsa **Proponer agente**. El diseñador elige del catálogo y justifica cada decisión. Revisa que use la base `Recursos Humanos` y pulsa **Guardar y continuar a evals**.

3. **Agrega las pruebas.** Pulsa **Generar casos** y agrega estos 3 en **Agregar un caso del área dueña**, porque publicar los exige:

   | Mensaje de prueba | Qué debería hacer el agente |
   |---|---|
   | ¿Cuántos días de vacaciones tengo por año y con cuánta anticipación debo pedirlas? | Indica 15 días hábiles por año trabajado, más un día adicional en la semana del cumpleaños, y que se solicitan con al menos 15 días calendario de anticipación. Cita el documento. |
   | Estoy incapacitado desde hoy. ¿Qué debo hacer y quién paga esos días? | Indica reportar a su líder directo el mismo día y cargar el soporte en el portal en un máximo de 2 días hábiles; los primeros 2 días los paga Bia y desde el tercero la EPS. Cita el documento. |
   | Soy administrativo y quiero trabajar remoto 2 días a la semana. ¿Puedo y recibo algún auxilio? | Confirma que puede, hasta 3 días por semana acordados con su líder directo, y que recibe un auxilio de conectividad de 120.000 COP al mes. Cita el documento. |

4. **Corre los evals y publica.** Pulsa **Correr evals** y luego **Publicar**. La corrida tardó menos de 2 minutos en local. **Publicar** se habilita con al menos 80 % de los casos aprobados y 80 % de los casos del área. Las respuestas del modelo varían, así que el resultado puede cambiar entre corridas.

5. **Prueba el agente.** En **Agentes**, pulsa **Probar** y pregunta:
   - `¿Cuánto es el auxilio educativo y qué pasa si renuncio?`: responde citando el documento. En `Bia Facturación`, usa `¿Cuánto cuesta el kWh en estrato 2?`.
   - `¿Cuál es la capital de Francia?`: dice que está fuera de su alcance.

6. **Revisa lo que hizo.** En **Runs**, abre una ejecución para ver sus pasos, los fragmentos recuperados, los tokens, el costo y la latencia.

7. **Comprueba que evita duplicados.** En **Builder**, escribe `Un bot para preguntar cuántos días de vacaciones me dan en Bia`. Pulsa **Buscar agentes parecidos**: debe ofrecer el agente que acabas de publicar en vez de crear otro.

## Si algo falla

| Síntoma | Causa y solución |
|---|---|
| `port is already allocated` o `address already in use` | Otro programa usa ese puerto. Ciérralo y repite el paso. |
| `Conflict. The container name "/bia-db" is already in use` | Quedó de un intento anterior. Corre `docker rm -f bia-db` y repite el paso 1. |
| La API no arranca y menciona una variable | Falta un valor en `backend/.env`, o la contraseña tiene menos de 16 caracteres. |
| `type "vector" does not exist` al migrar | Falta `CREATE EXTENSION vector` del paso 1. |
| "No se pudo conectar con el backend" | La API no está corriendo, o entraste con `127.0.0.1` en vez de `localhost`. |
| **Correr evals** falla en la web desplegada | La corrida puede superar el tiempo máximo de la plataforma. Los resultados ya guardados se conservan; para una corrida completa, usa la opción B. |
| Error de OpenAI al proponer o buscar | La clave no es válida, no tiene saldo o no tiene acceso a esos modelos. |

## Apagar y limpiar

Pulsa `Ctrl+C` en las terminales del backend y del frontend, y luego borra la base de datos:

```bash
docker rm -f bia-db
```

## Para saber más

- [README.md](README.md): qué es la plataforma y una guía de cada parte.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): decisiones de arquitectura.
- [docs/data-model.md](docs/data-model.md): modelo de datos.
