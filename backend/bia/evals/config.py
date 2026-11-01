from pydantic import BaseModel, ConfigDict, Field


class EvalsConfig(BaseModel):
    """Holds the numbers that decide what counts as tested enough.

    Exists to keep the rules of the publish gate, the generation and the monitoring in one place;
    consumed through `EVALS_CONFIG` by `bia/evals/`.
    """

    model_config = ConfigDict(frozen=True)

    publish_threshold_percent: int = Field(default=80, ge=0, le=100)
    minimum_cases_to_publish: int = Field(default=8, ge=1)  # so one easy case cannot open the gate
    minimum_generated_cases: int = Field(default=8, ge=1)
    maximum_generated_cases: int = Field(default=10, ge=1)
    minimum_out_of_scope_cases: int = Field(default=1, ge=0)
    passing_score: int = Field(default=70, ge=0, le=100)  # from here on, a score is a pass


EVALS_CONFIG = EvalsConfig()
