"""Tests for DhanDataService."""



from app.services.dhan_data import DhanDataService


class TestDhanDataService:
    def test_not_available_without_credentials(self) -> None:
        service = DhanDataService()
        assert service.available is False

    async def test_fetch_historical_not_available(self) -> None:
        from datetime import UTC, datetime

        service = DhanDataService()
        result = await service.fetch_historical("RELIANCE", "NSE", datetime.now(UTC), datetime.now(UTC))
        assert result == []

    async def test_fetch_vix_returns_none(self) -> None:
        service = DhanDataService()
        result = await service.fetch_vix()
        assert result is None

    async def test_fetch_nifty_return_not_available(self) -> None:
        service = DhanDataService()
        result = await service.fetch_nifty_return_5d()
        assert result is None

    async def test_fetch_earnings_returns_none(self) -> None:
        service = DhanDataService()
        result = await service.fetch_earnings_date("RELIANCE", "NSE")
        assert result is None

    async def test_fetch_intermarket_unavailable(self) -> None:
        service = DhanDataService()
        result = await service.fetch_intermarket_data()
        assert result == {"available": False}

    async def test_fetch_sector_rotation_empty(self) -> None:
        service = DhanDataService()
        result = await service.fetch_sector_rotation()
        assert result == {}
