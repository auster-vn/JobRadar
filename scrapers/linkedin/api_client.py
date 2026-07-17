from typing import Any

import httpx


class LinkedInApiClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("LinkedIn access token is required")
        self._client = httpx.AsyncClient(
            base_url="https://api.linkedin.com/v2",
            headers={
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": "202601",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=30,
        )

    async def __aenter__(self) -> "LinkedInApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        payload: object = response.json()
        if not isinstance(payload, dict):
            raise ValueError("LinkedIn API returned a non-object response")
        return payload
