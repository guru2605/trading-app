from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.trade import Trade
from app.schemas.trade import TradeResponse


class TradeService:
    def __init__(self, db: AsyncSession, kite: KiteClient | None = None) -> None:
        self.db = db
        self.kite = kite

    async def sync_trades(self) -> int:
        """Fetch today's trades from Kite and upsert into DB (dedup by order_id)."""
        if self.kite is None:
            raise RuntimeError("Kite client required for sync")

        kite_trades = await self.kite.trades()

        # Get existing order_ids for dedup
        result = await self.db.execute(select(Trade.order_id))
        existing_order_ids: set[str] = {row[0] for row in result.all()}

        inserted = 0
        for t in kite_trades:
            order_id = str(t.get("order_id", ""))
            if order_id in existing_order_ids:
                continue

            trade = Trade(
                order_id=order_id,
                exchange_order_id=str(t.get("exchange_order_id", "")),
                tradingsymbol=t.get("tradingsymbol", ""),
                exchange=t.get("exchange", ""),
                transaction_type=t.get("transaction_type", ""),
                quantity=t.get("quantity", 0),
                price=t.get("price", 0.0),
                product=t.get("product", ""),
                order_type=t.get("order_type", ""),
                status=t.get("status", "COMPLETE"),
                traded_at=t.get("fill_timestamp"),
            )
            self.db.add(trade)
            existing_order_ids.add(order_id)
            inserted += 1

        await self.db.commit()
        return inserted

    async def get_trades(
        self,
        tradingsymbol: str | None = None,
        transaction_type: str | None = None,
        limit: int = 50,
    ) -> list[TradeResponse]:
        """Get trades from DB with optional filters."""
        query = select(Trade)

        if tradingsymbol:
            query = query.where(Trade.tradingsymbol == tradingsymbol)
        if transaction_type:
            query = query.where(Trade.transaction_type == transaction_type)

        query = query.order_by(Trade.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        trades = list(result.scalars().all())
        return [TradeResponse.model_validate(t) for t in trades]
