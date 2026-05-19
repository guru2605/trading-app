from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.watchlist_item import WatchlistItem
from app.schemas.scanner import WatchlistItemResponse


class WatchlistService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_items(self) -> list[WatchlistItemResponse]:
        result = await self.db.execute(select(WatchlistItem).order_by(WatchlistItem.added_at.desc()))
        items = list(result.scalars().all())
        return [WatchlistItemResponse.model_validate(i) for i in items]

    async def add_item(self, tradingsymbol: str, exchange: str, notes: str) -> WatchlistItem:
        item = WatchlistItem(
            tradingsymbol=tradingsymbol.upper(),
            exchange=exchange.upper(),
            notes=notes,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete_item(self, item_id: int) -> bool:
        result = await self.db.execute(select(WatchlistItem).where(WatchlistItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            return False
        await self.db.delete(item)
        await self.db.commit()
        return True

    async def import_from_holdings(self) -> int:
        """Import symbols from holdings into watchlist, skipping duplicates."""
        result = await self.db.execute(select(Holding))
        holdings = list(result.scalars().all())
        if not holdings:
            return 0

        # Get existing watchlist symbols
        wl_result = await self.db.execute(select(WatchlistItem))
        existing = {(w.tradingsymbol, w.exchange) for w in wl_result.scalars().all()}

        added = 0
        for h in holdings:
            if (h.tradingsymbol, h.exchange) not in existing:
                self.db.add(
                    WatchlistItem(
                        tradingsymbol=h.tradingsymbol,
                        exchange=h.exchange,
                        notes=f"Imported from holdings (qty: {h.quantity})",
                    )
                )
                added += 1

        if added:
            await self.db.commit()
        return added
