from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str, admin_secret: str = ""):
        self.base_url = base_url.rstrip("/")
        self._admin_secret = admin_secret

    def _admin_headers(self) -> dict[str, str]:
        if not self._admin_secret:
            return {}
        return {"X-Admin-Secret": self._admin_secret}

    async def send_message(self, telegram_chat_id: int, message_text: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=35.0) as client:
            r = await client.post(
                f"{self.base_url}/v1/chat",
                json={"telegram_chat_id": telegram_chat_id, "message_text": message_text},
            )
            r.raise_for_status()
            return r.json()

    async def admin_get_discounts(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/discounts",
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_set_discounts(self, discounts: list[dict[str, Any]]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/discounts",
                json={"discounts": discounts},
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_set_price(self, membership_id: str, new_price: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/prices",
                json={"membership_id": membership_id, "new_price": new_price},
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_get_temporary(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/temporary-memberships",
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_upsert_temporary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/temporary-memberships",
                json={"items": items},
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_get_catalog(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/membership-catalog",
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_stats(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/stats",
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_refresh_user(self, telegram_chat_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/refresh-user",
                json={"telegram_chat_id": telegram_chat_id},
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_user_state(self, telegram_chat_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/user-state",
                params={"telegram_chat_id": telegram_chat_id},
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def admin_followup_now(self, telegram_chat_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/followup-now",
                json={"telegram_chat_id": telegram_chat_id},
                headers=self._admin_headers(),
            )
            r.raise_for_status()
            return r.json()
