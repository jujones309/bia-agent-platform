import {
  AgentKind,
  AgentStatus,
  EvalCaseOrigin,
  EvalVerdict,
  ModelSize,
  RunOrigin,
  RunStatus,
  StepType,
} from "@/lib/api/types";
import type {
  Agent,
  AgentInventoryItem,
  AgentVersion,
  CatalogModel,
  CatalogTool,
  EvalCaseOutcome,
  EvalReport,
  KnowledgeBase,
  RunRecord,
  RunStep,
} from "@/lib/api/types";

/** Builds an agent as the backend returns it. @returns The agent, with the overrides applied. */
export function buildAgent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "agent-1",
    name: "Bia Facturación",
    description: "Responde dudas de facturas.",
    owner_area: "Servicio al cliente",
    creator: "Ana",
    status: AgentStatus.DRAFT,
    kind: AgentKind.USER,
    active_version_number: 1,
    created_at: "2026-10-31T12:00:00Z",
    updated_at: "2026-10-31T12:00:00Z",
    ...overrides,
  };
}

/** Builds an agent version. @returns The version, with the overrides applied. */
export function buildVersion(overrides: Partial<AgentVersion> = {}): AgentVersion {
  return {
    id: "version-1",
    agent_id: "agent-1",
    version_number: 1,
    designer_justification: "model: es barato",
    created_at: "2026-10-31T12:00:00Z",
    spec: {
      purpose: "Responder dudas",
      system_prompt: "Eres el asistente.",
      model_id: "model-small",
      tool_names: ["consultar_factura"],
      knowledge_base_id: null,
      guardrails: ["No inventes saldos."],
      max_iterations: 5,
    },
    ...overrides,
  };
}

/** Builds a row of the agent inventory. @returns The row, with the overrides applied. */
export function buildInventoryItem(overrides: Partial<AgentInventoryItem> = {}): AgentInventoryItem {
  return {
    id: "agent-1",
    name: "Bia Facturación",
    owner_area: "Servicio al cliente",
    kind: AgentKind.USER,
    status: AgentStatus.PUBLISHED,
    active_version_number: 1,
    model_id: "model-small",
    model_name: "GPT-6 Luna",
    tool_names: [],
    knowledge_base_id: null,
    knowledge_base_name: null,
    total_runs: 1200,
    total_cost: "0.00137",
    ...overrides,
  };
}

/** The catalog models the tests choose from. */
export const MODELS: CatalogModel[] = [
  { id: "model-small", name: "GPT-6 Luna", size: ModelSize.SMALL, recommended_use: "Rápido" },
  { id: "model-large", name: "GPT-6.1 Sol", size: ModelSize.LARGE, recommended_use: "Complejo" },
];

/** The knowledge bases the tests choose from. */
export const KNOWLEDGE_BASES: KnowledgeBase[] = [
  { id: "base-1", name: "Facturación", description: "Tarifas y procedimientos", created_at: "2026-10-31T12:00:00Z" },
  { id: "base-2", name: "Talento", description: "Políticas internas", created_at: "2026-10-31T12:00:00Z" },
];

/** The catalog tools the tests choose from. */
export const TOOLS: CatalogTool[] = [
  { id: "tool-1", name: "consultar_factura", description: "Consulta facturas" },
  { id: "tool-2", name: "buscar_conocimiento", description: "Busca documentos" },
];

/** Builds a case that passed. @returns The case with its result. */
export function buildPassedOutcome(id = "case-1"): EvalCaseOutcome {
  return {
    case: {
      id,
      agent_id: "agent-1",
      input: "¿Cuál es mi saldo?",
      expected_behavior: "Pide el número de cliente",
      origin: EvalCaseOrigin.GENERATED,
      created_at: "2026-10-31T12:00:00Z",
    },
    result: { id: `result-${id}`, output: "Dime tu número", verdict: EvalVerdict.PASS, score: 90, judge_reason: "Cumple" },
  };
}

/** Builds a report of the active version. @returns The report, with the overrides applied. */
export function buildReport(overrides: Partial<EvalReport> = {}): EvalReport {
  return {
    agent_id: "agent-1",
    agent_version_id: "version-1",
    version_number: 1,
    threshold_percent: 80,
    minimum_cases: 8,
    total_cases: 0,
    passed_cases: 0,
    pass_percent: 0,
    passes_gate: false,
    outcomes: [],
    ...overrides,
  };
}

/** Builds a step of a run. @returns The step, with the overrides applied. */
export function buildStep(overrides: Partial<RunStep> = {}): RunStep {
  return {
    id: "step-1",
    run_id: "run-1",
    step_order: 1,
    step_type: StepType.LLM_CALL,
    model_id: "model-small",
    tool_id: null,
    input: [],
    output: "Hola",
    input_tokens: 120,
    output_tokens: 30,
    cost: "0.00016",
    latency_ms: 2500,
    error: null,
    created_at: "2026-10-31T12:00:00Z",
    ...overrides,
  };
}

/** Builds a finished run. @returns The run, with the overrides applied. */
export function buildRun(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: "run-1",
    agent_id: "agent-1",
    agent_version_id: "version-1",
    origin: RunOrigin.PLAYGROUND,
    input: "¿Cuál es mi saldo?",
    output: "Tu saldo es 100",
    status: RunStatus.SUCCEEDED,
    error: null,
    total_tokens: 150,
    total_cost: "0.00016",
    latency_ms: 7000,
    started_at: "2026-10-31T12:00:00Z",
    finished_at: "2026-10-31T12:00:07Z",
    steps: [buildStep()],
    ...overrides,
  };
}
