# CLAUDE.md

Guidance for Claude Code when writing or modifying code in this repository.

## What this project is

`bia-agent-platform` is an internal platform where any Bia employee can create an AI
agent on top of a **curated catalog of models and tools**, and where everything each
agent does is **recorded** (runs, steps, tokens, cost, latency). The first agent built
through the platform is the **customer-service billing assistant** (RAG over tariffs,
procedures and FAQs).

Core flow (the "Agent Builder"):

1. The user describes in natural language what they need.
2. **Duplicate detection**: semantic search (pgvector) over existing agents' descriptions,
   then an LLM judge decides `exists` / `similar` / `not_exists`.
3. If it exists, the user confirms it is the one they wanted.
4. If not, a **designer LLM** proposes the agent spec (purpose, system prompt, model,
   tools, knowledge base, guardrails), choosing **only** from the curated catalogs and
   storing its justification.
5. The user reviews and adjusts the spec.
6. Test cases are generated and evals run; the agent cannot be published below threshold.
7. The agent is published as a versioned spec.

An agent is **declarative, versioned configuration stored in the database**, never
generated code. A single generic runtime reads the spec and executes it.

## Stack

- **Backend**: Python 3.12 + FastAPI, deployed on Railway.
- **Database**: Supabase (Postgres + pgvector).
- **LLM**: OpenAI, always accessed through the `ModelProvider` abstraction.
- **Orchestration**: own tool-calling loop (no LangChain/LangGraph in the MVP).
- **Tracing**: own `runs` / `run_steps` tables.
- **Frontend**: Next.js on Vercel — built **last**; until then, demos run through
  FastAPI's Swagger UI (`/docs`).

## Project structure

```
bia-agent-platform/
├── backend/
│   ├── bia/            # the Python package (vertical slices, see below)
│   └── tests/          # mirrors bia/ 1:1
├── frontend/           # Next.js, final phase
├── docs/               # architecture document (the 6 questions of the brief)
└── README.md
```

The `bia` package (`backend/bia/`) is organized as **vertical slices**, not by technical
layer: each subdirectory directly under `bia/` is a single, self-contained concept, and
further nesting narrows that concept into concrete implementations. A vertical should be
understandable, testable, and replaceable without touching unrelated verticals.

Verticals:

| Vertical | Responsibility |
|---|---|
| `bia/catalog/models/` | Curated model catalog (name, provider, size, cost per token, intended use) |
| `bia/catalog/tools/` | Curated tool catalog and tool implementations agents may call |
| `bia/agents/` | Agent registry: agents, versions, specs, publishing |
| `bia/builder/` | Agent Builder: `duplicates/` (search + LLM judge) and `designer/` (spec proposal) |
| `bia/runtime/` | Generic executor: reads a spec, runs the tool-calling loop |
| `bia/tracing/` | Records runs and steps (tokens, cost, latency, tool calls) |
| `bia/rag/` | Document ingestion, chunking, embeddings, retrieval |
| `bia/evals/` | Test cases, eval runs, LLM-as-judge, publish gate |
| `bia/providers/` | `ModelProvider` contract; `providers/openai/` implementation |
| `bia/prompts/` | Shared loader of the `.md` prompts that live under `bia/<vertical>/prompts/` |
| `bia/database/` | Connection/session handling; `database/queries/` holds all SQL |
| `bia/api/` | FastAPI routers (thin layer, see below) |
| `bia/settings/` | Environment-driven settings (`pydantic-settings`) |

Example: `bia/providers/` holds the provider-agnostic contract; `bia/providers/openai/`
holds OpenAI-specific logic, which never leaks into sibling or consumer verticals.
Adding a new provider means adding a sibling directory, not editing consumers.

At the discretion of whoever is implementing a subpackage, but preferred by default,
each subpackage should expose:

- **`config.py`** — the subpackage's configuration, defined with pydantic `BaseModel`s.
- **`artifacts.py`** — the subpackage's contracts: the pydantic `BaseModel`s and typed
  return shapes that the subpackage's classes and functions produce or consume.

### API layer

The HTTP API is defined in `bia/api/` using FastAPI. Routers stay thin: validate input,
call into the relevant vertical under `bia/`, and return the result. Business logic
belongs in the vertical it concerns, never in a router.

`bia/api/` **mirrors the structure of `bia/`** where endpoints exist: `bia/agents/` gets
`bia/api/agents.py`, `bia/builder/` gets `bia/api/builder.py`, etc., each registered on
the root app (`bia/api/main.py`) via `app.include_router(...)`. A vertical with no
user-facing endpoints does not need a counterpart.

Request/response bodies reuse the vertical's `artifacts.py` models; do not duplicate
schemas in the API layer.

### Tests

`backend/tests/` **mirrors `backend/bia/` 1:1**, including `bia/api/`.
`bia/builder/duplicates/judge.py` is tested by `tests/builder/duplicates/test_judge.py`;
`bia/api/agents.py` by `tests/api/test_agents.py`. Every directory under `tests/` gets
an `__init__.py` so same-named test files in different verticals don't collide.

Tests never call the real OpenAI API: use a fake `ModelProvider` implementation.
Real-LLM checks belong to `bia/evals/`, not to the unit test suite.

## LLM rules (project-specific)

- **Only through `ModelProvider`**: never import `openai` outside `bia/providers/openai/`.
  Every other vertical depends on the `ModelProvider` contract.
- **No hardcoded model names**: model identifiers come from the model catalog in the
  database. Code refers to catalog entries, never to a literal model string.
- **Every LLM call is traced**: any call made by the runtime, builder or evals goes
  through `bia/tracing/` and records tokens, cost and latency.
- **Prompts live in files, never as Python string literals**: platform prompts (builder
  judge, designer, eval judge…) live in `.md` files under `bia/<vertical>/prompts/`,
  loaded by a shared helper. Each prompt file opens with a comment explaining why it
  exists and where it is consumed. Agents' own system prompts live in their spec in the
  database.
- **Structured outputs**: when an LLM must return data (judge verdicts, agent specs),
  request structured output validated against a pydantic model from `artifacts.py`.
  Never parse free text with regexes.
- **The designer chooses, it does not invent**: model and tool choices are validated
  against the catalogs; an unknown id is a hard error.

## Clean code practices (mandatory)

Every change must follow these practices. Spaghetti code is not acceptable under any
circumstance — if a change starts to require it, stop and refactor instead.

- **Single Responsibility Principle**: a class, function, or method does exactly one thing.
- **Encapsulation**: keep internal state private; expose a minimal, intentional public interface.
- **Documentation**: every class, function, and method is documented per the rules below.
- **DRY / reuse over recreation**: search the repository for an existing utility before
  writing new logic. Reuse or extend it instead of rewriting.
- **Descriptive naming**: names state their purpose unambiguously. No guessable abbreviations.
- **Small, focused functions**: see the 40-line rule below.
- **Separation of concerns**: don't mix I/O, business logic, and presentation.
- **Explicit, complete signatures**: see the type-hint rule below.
- **Fail fast, explicit error handling**: validate inputs and raise clear errors close to
  the source. Never silently swallow exceptions.
- **Avoid deep nesting**: prefer guard clauses and early returns.
- **No dead code**: no commented-out code, no unused parameters, no speculative code paths.

## No hardcoded strings or values — use Enums

Never hardcode a "magic" string or value that represents one option out of a known,
fixed set (agent status, duplicate verdict, run step type, provider name, document type…).
Define an `Enum` (or `StrEnum`) and reference the member everywhere — never the raw
literal, not even in comparisons or default arguments.

- **Enums must have a docstring**: why the set exists and where it's consumed.
- **Document non-obvious members** with an inline comment.
- **Enums can drive polymorphic behavior**: an abstract base class can take an Enum
  member as a discriminator, with `typing.Literal[...]` or `Annotated` types enforcing
  valid inputs statically.

Example shape:

```python
class DuplicateVerdict(StrEnum):
    """The possible outcomes of checking a new agent request against the registry.

    Produced by `bia/builder/duplicates/` and consumed by the builder API to decide
    whether to ask the user for confirmation or move on to the designer.
    """

    EXISTS = "exists"
    SIMILAR = "similar"  # an agent covers part of the need; user decides
    NOT_EXISTS = "not_exists"
```

## No nested functions or methods

Do not define a function inside another function, or a method inside another method.
Extract it to a module-level function or a private (`_`-prefixed) method instead.

## Function and method length: 40-line limit

No function or method body may exceed 40 lines. Extract the excess into private helpers
(`_`-prefixed), each with a single responsibility. The public method should read as a
short sequence of calls to those helpers.

## Complete signatures

Every function and method has full type hints on every parameter and on the return type.

## Docstrings

### Classes

Every class docstring explains:

1. Why the class exists (the problem it solves).
2. Where it is expected to be consumed (calling module/layer).

### `__init__` methods

Every `__init__` documents each constructor parameter (name, type, and purpose).

### Functions and methods (all of them)

Every docstring contains, in this order:

1. A verb-first summary (e.g., "Validates...", "Builds...", "Retrieves...").
2. The justification for why it exists and where it is useful.
3. `Args`: each parameter with its meaning.
4. `Returns`: what is returned and what it represents.

Example shape:

```python
def select_model(requirements: AgentRequirements) -> CatalogModel:
    """Selects the catalog model that best fits an agent's requirements.

    Exists so the designer never picks a model outside the curated catalog;
    used by the builder when proposing a new agent spec.

    Args:
        requirements: The complexity, latency and cost needs inferred for the agent.

    Returns:
        CatalogModel: the chosen catalog entry, including its cost per token.
    """
```

## Pydantic usage

`pydantic` (`BaseModel`) is used for exactly three purposes:

1. **Configuration objects** — in a subpackage's `config.py`.
2. **Return contracts for important artifacts** — in a subpackage's `artifacts.py`
   (agent specs, judge verdicts, run records, retrieval results…).
3. **API request/response bodies** — which reuse the models from `artifacts.py`.

Do not introduce pydantic models for internal, throwaway, or purely local data.

## SQL statements live in `.sql` files, never as Python string literals

Never declare SQL (DDL or DML) as a Python string. All SQL lives in `.sql` files under
`bia/database/queries/<table>/`, one subdirectory per table:

- `bia/database/queries/<table>/table.sql` — the table's schema DDL.
- `bia/database/queries/<table>/<operation>.sql` — its queries (e.g. `insert.sql`,
  `search_by_embedding.sql`).

Python reads the file through a shared loader (`bia.database.queries.load_sql`) and
passes the text to the database client. It never builds or concatenates SQL strings;
values always go through bound parameters.

Do not create indexes unless the user explicitly asks for them for that table.

### SQL docstrings

Every `.sql` file opens with a `--` comment block explaining why it exists and where it
is consumed, and every CTE has its own short `--` comment above it.

`table.sql` files document every column (type and business meaning, one `--` line per
column). Column documentation must come from the agreed data model in `docs/` or from
the user — never invented from the column name alone. If it is missing, ask before
writing the `table.sql`.

## Logging

Never use `print`. All output goes through the standard `logging` module.

- Logs read as a step-by-step narrative ("Searching registry for similar agents",
  "Judge verdict: similar (agent_id=…)", "Run {id} finished in {ms} ms, cost ${cost}").
- Use the appropriate level: `debug` internal detail, `info` normal progress, `warning`
  recoverable issues, `error`/`exception` failures.
- Use `logging.getLogger(__name__)`; configure handlers only at the app entrypoint
  (`bia/api/main.py`).
- Logging is for operators; the **audit record** of what agents do lives in
  `bia/tracing/`, not in logs.
- Never log secrets, API keys, or full end-customer personal data.

## Configuration and secrets

- All settings come from environment variables through `bia/settings/`
  (`pydantic-settings`), read from `backend/.env` locally and from Railway variables in
  production.
- `.env` is never committed; `backend/.env.example` lists every required variable.

## README

`README.md` (root, in Spanish) explains the project and how to do everything built so far.
A plan phase in `docs/PLAN.md` is not finished until the README is updated in that phase:

- Add a `## Guía: fase N — <tema>` section with the how-to of each thing the phase added
  (commands to run, how to use or extend it, required variables, limitations).
- Update the `## Estado` table and any earlier section the phase made outdated.
- Only document what exists and was actually run; never describe planned behavior as working.

## Testing philosophy

Tests verify the actual behavior and intent of the code, not just exercise it.

- Understand what the unit is *for* and assert outcomes that would fail if that problem
  were reintroduced.
- No trivial assertions ("runs without error", "mock was called", "is not None" when a
  concrete value can be checked).
- Cover meaningful edge cases and failure modes, not just the happy path.
- A test that still passes after the logic is broken is worse than no test.

## Dependency management: always use `uv`

Never hand-edit `pyproject.toml` dependencies or `uv.lock`. Always use `uv`
(`uv add`, `uv remove`, `uv add --upgrade-package`). Run commands from `backend/`
with `uv run …`.

## Commit messages

Conventional Commits: `<type>(<scope>): <description>`.

- `type`: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `style`, `perf`.
- `scope`: the vertical or area (`builder`, `builder/duplicates`, `runtime`, `rag`,
  `api`, `frontend`, `docs`).
- `description`: short, imperative ("add", not "added").

Example: `feat(builder/duplicates): add LLM judge for similar agents`.

## Frontend (TypeScript/React) — final phase

`frontend/` is a separate Next.js + TypeScript project, excluded from the Python tooling.
The same standards apply, adapted:

- **Tests mirror the source tree**: `frontend/tests/` mirrors `frontend/src/` 1:1.
- **TSDoc on every exported component, hook, and function**: what it does, why it
  exists, `@param`s, and return value.
- **No magic strings**: use `enum` or `as const` objects for fixed sets (agent status,
  verdicts, routes…). Backend enums should be mirrored, not retyped as literals.
- **40-line limit** per component, hook, and function.
- **No `console.*`**: errors and notable events go through a single logging helper.
- **API access through one client module**: components never call `fetch` directly.
- **Inline callbacks only as direct hook arguments or JSX props**, and they must
  immediately delegate to a named function (`onClick={() => handlePublish()}`).
