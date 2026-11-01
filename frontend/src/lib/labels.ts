import {
  AgentStatus,
  EvalVerdict,
  ModelSize,
  OrchestrationType,
  RunOrigin,
  RunStatus,
  StepType,
} from "@/lib/api/types";

/** The Spanish name of each agent status; consumed by the inventories and the review page. */
export const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  [AgentStatus.DRAFT]: "Borrador",
  [AgentStatus.TESTING]: "En pruebas",
  [AgentStatus.PUBLISHED]: "Publicado",
  [AgentStatus.ARCHIVED]: "Archivado",
};

/** The Spanish name of each run status; consumed by the trace views and the playground. */
export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  [RunStatus.RUNNING]: "En curso",
  [RunStatus.SUCCEEDED]: "Exitoso",
  [RunStatus.FAILED]: "Fallido",
};

/** The Spanish name of each run origin; consumed by the trace views. */
export const RUN_ORIGIN_LABEL: Record<RunOrigin, string> = {
  [RunOrigin.PLAYGROUND]: "Playground",
  [RunOrigin.EVAL]: "Evals",
  [RunOrigin.BUILDER]: "Builder",
  [RunOrigin.PRODUCTION]: "Producción",
};

/** The Spanish name of each step type; consumed by the trace view. */
export const STEP_TYPE_LABEL: Record<StepType, string> = {
  [StepType.LLM_CALL]: "Llamada al modelo",
  [StepType.TOOL_CALL]: "Herramienta",
  [StepType.RETRIEVAL]: "Búsqueda",
};

/** The Spanish name of each eval verdict; consumed by the eval step. */
export const EVAL_VERDICT_LABEL: Record<EvalVerdict, string> = {
  [EvalVerdict.PASS]: "Aprobado",
  [EvalVerdict.FAIL]: "Fallido",
};

/** The Spanish name of each model size; consumed by the model inventory and the spec form. */
export const MODEL_SIZE_LABEL: Record<ModelSize, string> = {
  [ModelSize.LARGE]: "Grande",
  [ModelSize.SMALL]: "Pequeño",
  [ModelSize.EMBEDDING]: "Embeddings",
};

/** The Spanish name of each flow shape; consumed by the orchestration inventory. */
export const ORCHESTRATION_TYPE_LABEL: Record<OrchestrationType, string> = {
  [OrchestrationType.SINGLE_AGENT]: "Un agente",
  [OrchestrationType.SEQUENTIAL]: "Secuencial",
};
