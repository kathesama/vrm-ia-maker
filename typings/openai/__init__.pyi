from typing import Any

class OpenAI:
    images: Any

    def __init__(
        self,
        *,
        api_key: str,
        max_retries: int,
        timeout: float,
    ) -> None: ...
