from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.risk_snapshot import RiskSnapshot
from app.models.sector_map import SectorMap
from app.schemas.risk import RiskSnapshotResponse


class RiskSnapshotService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_snapshot(self) -> RiskSnapshot:
        """Create a risk snapshot from current holdings."""
        result = await self.db.execute(select(Holding).where(Holding.quantity > 0))
        holdings = list(result.scalars().all())

        total_invested = sum(h.average_price * h.quantity for h in holdings)
        total_current = sum(h.last_price * h.quantity for h in holdings)
        total_pnl = total_current - total_invested
        day_pnl = sum(h.day_change * h.quantity for h in holdings)

        # Max single stock concentration
        max_single_stock_pct = 0.0
        if total_current > 0:
            max_single_stock_pct = (
                max((h.last_price * h.quantity / total_current * 100) for h in holdings) if holdings else 0.0
            )

        # Sector concentration
        symbols = [h.tradingsymbol for h in holdings]
        sector_result = await self.db.execute(select(SectorMap).where(SectorMap.tradingsymbol.in_(symbols)))
        sector_lookup: dict[str, str] = {s.tradingsymbol: s.sector for s in sector_result.scalars().all()}

        sector_values: dict[str, float] = {}
        for h in holdings:
            sector = sector_lookup.get(h.tradingsymbol, "Unknown")
            value = h.last_price * h.quantity
            sector_values[sector] = sector_values.get(sector, 0.0) + value

        sector_concentration: dict[str, Any] = {}
        if total_current > 0:
            sector_concentration = {
                sector: round(value / total_current * 100, 2) for sector, value in sector_values.items()
            }

        # Per-holding details
        details: dict[str, Any] = {
            "holdings": [
                {
                    "tradingsymbol": h.tradingsymbol,
                    "quantity": h.quantity,
                    "current_value": round(h.last_price * h.quantity, 2),
                    "pnl": round(h.pnl, 2),
                }
                for h in holdings
            ]
        }

        snapshot = RiskSnapshot(
            snapshot_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            total_invested=round(total_invested, 2),
            total_current=round(total_current, 2),
            total_pnl=round(total_pnl, 2),
            day_pnl=round(day_pnl, 2),
            max_single_stock_pct=round(max_single_stock_pct, 2),
            sector_concentration=sector_concentration,
            details=details,
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def list_snapshots(self, limit: int = 30) -> list[RiskSnapshotResponse]:
        """Get snapshot history ordered by date descending."""
        query = select(RiskSnapshot).order_by(RiskSnapshot.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        snapshots = list(result.scalars().all())
        return [RiskSnapshotResponse.model_validate(s) for s in snapshots]

    async def get_latest(self) -> RiskSnapshotResponse | None:
        """Get the most recent snapshot."""
        query = select(RiskSnapshot).order_by(RiskSnapshot.created_at.desc()).limit(1)
        result = await self.db.execute(query)
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return None
        return RiskSnapshotResponse.model_validate(snapshot)
