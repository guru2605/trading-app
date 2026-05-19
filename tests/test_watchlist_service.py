import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.watchlist import WatchlistService


@pytest.fixture
def watchlist_service(db_session: AsyncSession) -> WatchlistService:
    return WatchlistService(db_session)


class TestWatchlistService:
    async def test_add_item(self, watchlist_service: WatchlistService) -> None:
        item = await watchlist_service.add_item("RELIANCE", "NSE", "Top pick")
        assert item.tradingsymbol == "RELIANCE"
        assert item.exchange == "NSE"
        assert item.notes == "Top pick"
        assert item.id is not None

    async def test_add_item_uppercases(self, watchlist_service: WatchlistService) -> None:
        item = await watchlist_service.add_item("reliance", "nse", "")
        assert item.tradingsymbol == "RELIANCE"
        assert item.exchange == "NSE"

    async def test_list_items_empty(self, watchlist_service: WatchlistService) -> None:
        items = await watchlist_service.list_items()
        assert items == []

    async def test_list_items_returns_added(self, watchlist_service: WatchlistService) -> None:
        await watchlist_service.add_item("RELIANCE", "NSE", "")
        await watchlist_service.add_item("TCS", "NSE", "IT sector")
        items = await watchlist_service.list_items()
        assert len(items) == 2
        symbols = {i.tradingsymbol for i in items}
        assert symbols == {"RELIANCE", "TCS"}

    async def test_delete_item(self, watchlist_service: WatchlistService) -> None:
        item = await watchlist_service.add_item("RELIANCE", "NSE", "")
        deleted = await watchlist_service.delete_item(item.id)
        assert deleted is True
        items = await watchlist_service.list_items()
        assert len(items) == 0

    async def test_delete_nonexistent(self, watchlist_service: WatchlistService) -> None:
        deleted = await watchlist_service.delete_item(999)
        assert deleted is False
