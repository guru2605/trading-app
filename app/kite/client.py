import asyncio
from datetime import datetime
from typing import Any

from kiteconnect import KiteConnect


class KiteClient:
    """Async wrapper around the synchronous KiteConnect SDK."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)

    async def holdings(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await asyncio.to_thread(self._kite.holdings)
        return result

    async def positions(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = await asyncio.to_thread(self._kite.positions)
        return result

    async def orders(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await asyncio.to_thread(self._kite.orders)
        return result

    async def trades(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await asyncio.to_thread(self._kite.trades)
        return result

    async def margins(self, segment: str | None = None) -> dict[str, Any]:
        if segment:
            result: dict[str, Any] = await asyncio.to_thread(self._kite.margins, segment)
        else:
            result = await asyncio.to_thread(self._kite.margins)
        return result

    async def ltp(self, instruments: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = await asyncio.to_thread(self._kite.ltp, instruments)
        return result

    async def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day",
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await asyncio.to_thread(
            self._kite.historical_data,
            instrument_token,
            from_date,
            to_date,
            interval,
        )
        return result

    async def place_order(
        self,
        variety: str,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        product: str,
        order_type: str,
        price: float | None = None,
        trigger_price: float | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "variety": variety,
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "product": product,
            "order_type": order_type,
        }
        if price is not None:
            kwargs["price"] = price
        if trigger_price is not None:
            kwargs["trigger_price"] = trigger_price
        order_id: str = await asyncio.to_thread(self._kite.place_order, **kwargs)
        return order_id

    async def cancel_order(self, variety: str, order_id: str) -> str:
        result: str = await asyncio.to_thread(self._kite.cancel_order, variety, order_id)
        return result

    async def order_margins(self, params: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await asyncio.to_thread(self._kite.order_margins, params)
        return result
