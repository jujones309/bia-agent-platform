from pydantic import BaseModel, Field


class OpenAIProviderConfig(BaseModel):
    """Holds the connection behavior of the OpenAI client.

    Exists to keep timeouts and retries in one place, separate from the secrets in
    `bia/settings/`. Consumed by `build_openai_provider`.
    """

    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=2, ge=0)
