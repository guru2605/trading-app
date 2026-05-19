from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.holding import Holding
from app.models.sector_map import SectorMap
from app.schemas.portfolio import (
    AllocationItem,
    AllocationResponse,
    HoldingResponse,
    PortfolioSummary,
)


class PortfolioService:
    def __init__(self, db: AsyncSession, kite: KiteClient | None = None) -> None:
        self.db = db
        self.kite = kite

    async def sync_holdings(self) -> int:
        """Fetch holdings from Kite and upsert into DB."""
        if self.kite is None:
            raise RuntimeError("Kite client required for sync")
        kite_holdings = await self.kite.holdings()
        now = datetime.now(UTC)

        # Get existing holdings keyed by tradingsymbol
        result = await self.db.execute(select(Holding))
        existing = {h.tradingsymbol: h for h in result.scalars().all()}
        seen: set[str] = set()

        for h in kite_holdings:
            symbol = h["tradingsymbol"]
            seen.add(symbol)

            if symbol in existing:
                holding = existing[symbol]
                holding.exchange = h.get("exchange", holding.exchange)
                holding.isin = h.get("isin", holding.isin)
                holding.quantity = h.get("quantity", 0)
                holding.average_price = h.get("average_price", 0.0)
                holding.last_price = h.get("last_price", 0.0)
                holding.pnl = h.get("pnl", 0.0)
                holding.day_change = h.get("day_change", 0.0)
                holding.day_change_pct = h.get("day_change_percentage", 0.0)
                holding.synced_at = now
            else:
                holding = Holding(
                    tradingsymbol=symbol,
                    exchange=h.get("exchange", ""),
                    isin=h.get("isin", ""),
                    quantity=h.get("quantity", 0),
                    average_price=h.get("average_price", 0.0),
                    last_price=h.get("last_price", 0.0),
                    pnl=h.get("pnl", 0.0),
                    day_change=h.get("day_change", 0.0),
                    day_change_pct=h.get("day_change_percentage", 0.0),
                    synced_at=now,
                )
                self.db.add(holding)

        # Zero out exited positions
        for symbol, holding in existing.items():
            if symbol not in seen:
                holding.quantity = 0
                holding.last_price = 0.0
                holding.pnl = 0.0
                holding.day_change = 0.0
                holding.day_change_pct = 0.0
                holding.synced_at = now

        await self.db.commit()
        return len(kite_holdings)

    async def get_holdings(self) -> list[HoldingResponse]:
        """Get holdings from DB with computed weights."""
        result = await self.db.execute(select(Holding).where(Holding.quantity > 0))
        holdings = list(result.scalars().all())

        total_value = sum(h.last_price * h.quantity for h in holdings)

        responses: list[HoldingResponse] = []
        for h in holdings:
            current_value = h.last_price * h.quantity
            weight = (current_value / total_value * 100) if total_value > 0 else 0.0
            resp = HoldingResponse.model_validate(h)
            resp.weight = round(weight, 2)
            responses.append(resp)

        return responses

    async def get_summary(self) -> PortfolioSummary:
        """Compute aggregated portfolio summary."""
        result = await self.db.execute(select(Holding).where(Holding.quantity > 0))
        holdings = list(result.scalars().all())

        total_invested = sum(h.average_price * h.quantity for h in holdings)
        total_current = sum(h.last_price * h.quantity for h in holdings)
        total_pnl = total_current - total_invested
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        day_pnl = sum(h.day_change * h.quantity for h in holdings)
        day_pnl_pct = (day_pnl / total_current * 100) if total_current > 0 else 0.0

        return PortfolioSummary(
            total_invested=round(total_invested, 2),
            total_current=round(total_current, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 2),
            day_pnl=round(day_pnl, 2),
            day_pnl_pct=round(day_pnl_pct, 2),
            holdings_count=len(holdings),
        )

    async def get_allocation(self) -> AllocationResponse:
        """Get sector-wise allocation by joining holdings with sector_maps."""
        result = await self.db.execute(select(Holding).where(Holding.quantity > 0))
        holdings = list(result.scalars().all())

        symbols = [h.tradingsymbol for h in holdings]
        sector_result = await self.db.execute(select(SectorMap).where(SectorMap.tradingsymbol.in_(symbols)))
        sector_lookup: dict[str, str] = {s.tradingsymbol: s.sector for s in sector_result.scalars().all()}

        sector_data: dict[str, dict[str, Any]] = {}
        total_value = 0.0

        for h in holdings:
            sector = sector_lookup.get(h.tradingsymbol, "Unknown")
            value = h.last_price * h.quantity
            total_value += value

            if sector not in sector_data:
                sector_data[sector] = {"value": 0.0, "count": 0}
            sector_data[sector]["value"] += value
            sector_data[sector]["count"] += 1

        allocations = [
            AllocationItem(
                sector=sector,
                value=round(data["value"], 2),
                weight=round(data["value"] / total_value * 100, 2) if total_value > 0 else 0.0,
                holdings_count=data["count"],
            )
            for sector, data in sorted(sector_data.items(), key=lambda x: x[1]["value"], reverse=True)
        ]

        return AllocationResponse(allocations=allocations, total_value=round(total_value, 2))

    async def get_exposure(self) -> dict[str, Any]:
        """Compute exposure metrics from holdings and positions."""
        result = await self.db.execute(select(Holding).where(Holding.quantity > 0))
        holdings = list(result.scalars().all())

        long_exposure = sum(h.last_price * h.quantity for h in holdings if h.quantity > 0)

        # Fetch live positions for short exposure
        try:
            if self.kite is None:
                raise ValueError("No Kite client")
            positions_data = await self.kite.positions()
            net_positions = positions_data.get("net", [])
            short_exposure = sum(
                abs(p.get("last_price", 0) * p.get("quantity", 0)) for p in net_positions if p.get("quantity", 0) < 0
            )
            long_exposure += sum(
                p.get("last_price", 0) * p.get("quantity", 0) for p in net_positions if p.get("quantity", 0) > 0
            )
        except Exception:
            short_exposure = 0.0

        total_exposure = long_exposure + short_exposure
        net_exposure = long_exposure - short_exposure
        leverage = total_exposure / long_exposure if long_exposure > 0 else 0.0

        if net_exposure > 0:
            directional_bias = "long"
        elif net_exposure < 0:
            directional_bias = "short"
        else:
            directional_bias = "neutral"

        return {
            "total_exposure": round(total_exposure, 2),
            "net_exposure": round(net_exposure, 2),
            "long_exposure": round(long_exposure, 2),
            "short_exposure": round(short_exposure, 2),
            "leverage": round(leverage, 2),
            "directional_bias": directional_bias,
        }
