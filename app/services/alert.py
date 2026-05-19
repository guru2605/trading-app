from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.alert import Alert
from app.schemas.alert import AlertCheckResult, AlertResponse


class AlertService:
    def __init__(self, db: AsyncSession, kite: KiteClient | None = None) -> None:
        self.db = db
        self.kite = kite

    async def create_alert(
        self,
        tradingsymbol: str,
        exchange: str,
        alert_type: str,
        target_value: float,
    ) -> Alert:
        alert = Alert(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            alert_type=alert_type,
            target_value=target_value,
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def list_alerts(self, is_active: bool | None = None) -> list[AlertResponse]:
        query = select(Alert).order_by(Alert.created_at.desc())
        if is_active is not None:
            query = query.where(Alert.is_active == is_active)
        result = await self.db.execute(query)
        alerts = list(result.scalars().all())
        return [AlertResponse.model_validate(a) for a in alerts]

    async def update_alert(
        self,
        alert_id: int,
        target_value: float | None = None,
        is_active: bool | None = None,
    ) -> Alert | None:
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if alert is None:
            return None

        if target_value is not None:
            alert.target_value = target_value
        if is_active is not None:
            alert.is_active = is_active

        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def delete_alert(self, alert_id: int) -> bool:
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if alert is None:
            return False
        await self.db.delete(alert)
        await self.db.commit()
        return True

    async def check_alerts(self) -> list[AlertCheckResult]:
        """Check all active alerts against live LTP from Kite."""
        if self.kite is None:
            raise RuntimeError("Kite client required for alert checking")

        result = await self.db.execute(
            select(Alert).where(Alert.is_active == True)  # noqa: E712
        )
        alerts = list(result.scalars().all())

        if not alerts:
            return []

        # Build instrument keys for LTP call
        instruments = list({f"{a.exchange}:{a.tradingsymbol}" for a in alerts})
        ltp_data = await self.kite.ltp(instruments)

        results: list[AlertCheckResult] = []
        now = datetime.now(UTC)

        for alert in alerts:
            key = f"{alert.exchange}:{alert.tradingsymbol}"
            price_info = ltp_data.get(key, {})
            current_price = price_info.get("last_price", 0.0)

            triggered = False
            if (alert.alert_type == "price_above" and current_price >= alert.target_value) or (
                alert.alert_type == "price_below" and current_price <= alert.target_value
            ):
                triggered = True
            elif alert.alert_type == "pct_change" and current_price > 0:
                # pct_change: target_value is the threshold percentage
                # We compare absolute day change percentage
                change_pct = (
                    abs(
                        (current_price - price_info.get("close", current_price))
                        / price_info.get("close", current_price)
                        * 100
                    )
                    if price_info.get("close")
                    else 0.0
                )
                if change_pct >= alert.target_value:
                    triggered = True

            if triggered:
                alert.triggered_at = now
                alert.is_active = False

            results.append(
                AlertCheckResult(
                    tradingsymbol=alert.tradingsymbol,
                    alert_type=alert.alert_type,
                    target_value=alert.target_value,
                    current_price=current_price,
                    triggered=triggered,
                )
            )

        await self.db.commit()
        return results
