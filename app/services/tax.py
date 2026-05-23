import csv
import io
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_lot import TaxLot
from app.models.trade import Trade
from app.schemas.tax import (
    DailyTaxEstimate,
    TaxComputeResponse,
    TaxLotResponse,
    TaxSummaryResponse,
    WashSaleResponse,
)

STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_EXEMPTION = 125000.0


def parse_fy(fy: str | None) -> tuple[datetime, datetime]:
    """Parse FY string like '2025-2026' into (start, end) datetimes."""
    if fy:
        parts = fy.split("-")
        start_year = int(parts[0])
    else:
        today = date.today()
        start_year = today.year if today.month >= 4 else today.year - 1

    start = datetime(start_year, 4, 1, tzinfo=UTC)
    end = datetime(start_year + 1, 3, 31, 23, 59, 59, tzinfo=UTC)
    return start, end


def format_fy(start: datetime) -> str:
    return f"{start.year}-{start.year + 1}"


class TaxService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def compute_tax_lots(self, fy: str | None = None) -> TaxComputeResponse:
        """FIFO lot matching from trades for a given FY."""
        fy_start, fy_end = parse_fy(fy)
        lots_created = 0
        lots_updated = 0

        # Step 1: Create BUY lots for any BUY trades that don't have a lot yet
        buy_trades_result = await self.db.execute(
            select(Trade)
            .where(
                Trade.transaction_type == "BUY",
                Trade.status == "COMPLETE",
            )
            .order_by(Trade.traded_at.asc())
        )
        buy_trades = list(buy_trades_result.scalars().all())

        for bt in buy_trades:
            existing = await self.db.execute(
                select(TaxLot).where(
                    TaxLot.tradingsymbol == bt.tradingsymbol,
                    TaxLot.buy_date == bt.traded_at,
                    TaxLot.buy_price == bt.price,
                    TaxLot.quantity == bt.quantity,
                )
            )
            if existing.scalar_one_or_none() is None:
                lot = TaxLot(
                    tradingsymbol=bt.tradingsymbol,
                    exchange=bt.exchange,
                    buy_date=bt.traded_at,
                    buy_price=bt.price,
                    quantity=bt.quantity,
                    remaining_quantity=bt.quantity,
                    holding_type="LTCG",
                )
                self.db.add(lot)
                lots_created += 1

        await self.db.flush()

        # Step 2: Process SELL trades within the FY
        sell_trades_result = await self.db.execute(
            select(Trade)
            .where(
                Trade.transaction_type == "SELL",
                Trade.status == "COMPLETE",
                Trade.traded_at >= fy_start,
                Trade.traded_at <= fy_end,
            )
            .order_by(Trade.traded_at.asc())
        )
        sell_trades = list(sell_trades_result.scalars().all())

        for st in sell_trades:
            remaining_sell_qty = st.quantity
            is_intraday = self._is_intraday(st, buy_trades)

            # Find open BUY lots for same symbol, FIFO order
            open_lots_result = await self.db.execute(
                select(TaxLot)
                .where(
                    TaxLot.tradingsymbol == st.tradingsymbol,
                    TaxLot.remaining_quantity > 0,
                )
                .order_by(TaxLot.buy_date.asc())
            )
            open_lots = list(open_lots_result.scalars().all())

            for lot in open_lots:
                if remaining_sell_qty <= 0:
                    break

                matched_qty = min(lot.remaining_quantity, remaining_sell_qty)

                if matched_qty < lot.remaining_quantity:
                    # Partial consumption: split the lot
                    sold_lot = TaxLot(
                        tradingsymbol=lot.tradingsymbol,
                        exchange=lot.exchange,
                        buy_date=lot.buy_date,
                        buy_price=lot.buy_price,
                        quantity=matched_qty,
                        remaining_quantity=0,
                        sell_date=st.traded_at,
                        sell_price=st.price,
                        realized_pnl=round((st.price - lot.buy_price) * matched_qty, 2),
                        holding_type=self._classify_holding(lot.buy_date, st.traded_at, is_intraday, st.product),
                    )
                    self.db.add(sold_lot)
                    lot.remaining_quantity -= matched_qty
                    lots_created += 1
                    lots_updated += 1
                else:
                    # Full consumption
                    lot.remaining_quantity = 0
                    lot.sell_date = st.traded_at
                    lot.sell_price = st.price
                    lot.realized_pnl = round((st.price - lot.buy_price) * matched_qty, 2)
                    lot.holding_type = self._classify_holding(lot.buy_date, st.traded_at, is_intraday, st.product)
                    lots_updated += 1

                remaining_sell_qty -= matched_qty

        await self.db.commit()
        return TaxComputeResponse(
            lots_created=lots_created,
            lots_updated=lots_updated,
            message=f"Computed tax lots for FY {format_fy(fy_start)}.",
        )

    async def get_summary(self, fy: str | None = None) -> TaxSummaryResponse:
        """Get STCG/LTCG/intraday/F&O summary with estimated tax for a FY."""
        fy_start, fy_end = parse_fy(fy)

        result = await self.db.execute(
            select(TaxLot).where(
                TaxLot.sell_date >= fy_start,
                TaxLot.sell_date <= fy_end,
                TaxLot.realized_pnl.isnot(None),
            )
        )
        lots = list(result.scalars().all())

        total_stcg = 0.0
        total_ltcg = 0.0
        total_intraday = 0.0
        total_fno = 0.0

        for lot in lots:
            pnl = lot.realized_pnl or 0.0
            if lot.holding_type == "INTRADAY":
                total_intraday += pnl
            elif lot.holding_type == "FNO":
                total_fno += pnl
            elif lot.holding_type == "STCG":
                total_stcg += pnl
            else:
                total_ltcg += pnl

        estimated_stcg_tax = max(total_stcg * STCG_RATE, 0.0)
        ltcg_taxable = max(total_ltcg - LTCG_EXEMPTION, 0.0)
        estimated_ltcg_tax = round(ltcg_taxable * LTCG_RATE, 2)

        return TaxSummaryResponse(
            total_stcg=round(total_stcg, 2),
            total_ltcg=round(total_ltcg, 2),
            total_intraday=round(total_intraday, 2),
            total_fno=round(total_fno, 2),
            estimated_stcg_tax=round(estimated_stcg_tax, 2),
            estimated_ltcg_tax=estimated_ltcg_tax,
            fy=format_fy(fy_start),
        )

    async def get_lots(
        self,
        fy: str | None = None,
        tradingsymbol: str | None = None,
        holding_type: str | None = None,
    ) -> list[TaxLotResponse]:
        """Get tax lots with optional filters."""
        fy_start, fy_end = parse_fy(fy)

        query = select(TaxLot).where(
            TaxLot.buy_date <= fy_end,
        )

        if tradingsymbol:
            query = query.where(TaxLot.tradingsymbol == tradingsymbol)
        if holding_type:
            query = query.where(TaxLot.holding_type == holding_type)

        query = query.order_by(TaxLot.buy_date.asc())
        result = await self.db.execute(query)
        lots = list(result.scalars().all())
        return [TaxLotResponse.model_validate(lot) for lot in lots]

    async def get_daily_estimate(self, fy: str | None = None) -> list[DailyTaxEstimate]:
        """Compute running daily tax liability estimate for the FY."""
        fy_start, fy_end = parse_fy(fy)

        result = await self.db.execute(
            select(TaxLot)
            .where(
                TaxLot.sell_date >= fy_start,
                TaxLot.sell_date <= fy_end,
                TaxLot.realized_pnl.isnot(None),
            )
            .order_by(TaxLot.sell_date.asc())
        )
        lots = list(result.scalars().all())

        if not lots:
            return []

        # Group realized P&L by sell date
        daily_pnl: dict[date, dict[str, float]] = defaultdict(
            lambda: {"stcg": 0.0, "ltcg": 0.0, "intraday": 0.0, "fno": 0.0}
        )
        for lot in lots:
            if lot.sell_date is None:
                continue
            sell_day = lot.sell_date.date() if isinstance(lot.sell_date, datetime) else lot.sell_date
            pnl = lot.realized_pnl or 0.0
            if lot.holding_type == "INTRADAY":
                daily_pnl[sell_day]["intraday"] += pnl
            elif lot.holding_type == "FNO":
                daily_pnl[sell_day]["fno"] += pnl
            elif lot.holding_type == "STCG":
                daily_pnl[sell_day]["stcg"] += pnl
            else:
                daily_pnl[sell_day]["ltcg"] += pnl

        # Build running totals
        sorted_dates = sorted(daily_pnl.keys())
        estimates: list[DailyTaxEstimate] = []
        cum_stcg = 0.0
        cum_ltcg = 0.0
        cum_intraday = 0.0
        cum_fno = 0.0

        for d in sorted_dates:
            cum_stcg += daily_pnl[d]["stcg"]
            cum_ltcg += daily_pnl[d]["ltcg"]
            cum_intraday += daily_pnl[d]["intraday"]
            cum_fno += daily_pnl[d]["fno"]

            stcg_tax = max(cum_stcg * STCG_RATE, 0.0)
            ltcg_taxable = max(cum_ltcg - LTCG_EXEMPTION, 0.0)
            ltcg_tax = ltcg_taxable * LTCG_RATE
            estimated_tax = round(stcg_tax + ltcg_tax, 2)

            advance_tax_due = self._advance_tax_due(d, estimated_tax, fy_start)

            estimates.append(
                DailyTaxEstimate(
                    date=d,
                    stcg_to_date=round(cum_stcg, 2),
                    ltcg_to_date=round(cum_ltcg, 2),
                    intraday_to_date=round(cum_intraday, 2),
                    fno_to_date=round(cum_fno, 2),
                    estimated_tax=estimated_tax,
                    advance_tax_due=round(advance_tax_due, 2),
                )
            )

        return estimates

    async def detect_wash_sales(self, fy: str | None = None) -> list[WashSaleResponse]:
        """Detect re-buys within 30 days after a loss sale (advisory)."""
        fy_start, fy_end = parse_fy(fy)

        # Get SELL trades at a loss within the FY
        loss_lots_result = await self.db.execute(
            select(TaxLot).where(
                TaxLot.sell_date >= fy_start,
                TaxLot.sell_date <= fy_end,
                TaxLot.realized_pnl < 0,
            )
        )
        loss_lots = list(loss_lots_result.scalars().all())

        wash_sales: list[WashSaleResponse] = []
        for lot in loss_lots:
            sell_dt = lot.sell_date
            if sell_dt is None:
                continue

            # Check for re-buy within 30 days
            rebuy_result = await self.db.execute(
                select(Trade)
                .where(
                    Trade.tradingsymbol == lot.tradingsymbol,
                    Trade.transaction_type == "BUY",
                    Trade.status == "COMPLETE",
                    Trade.traded_at > sell_dt,
                    Trade.traded_at <= sell_dt + timedelta(days=30),
                )
                .order_by(Trade.traded_at.asc())
                .limit(1)
            )
            rebuy = rebuy_result.scalar_one_or_none()
            if rebuy:
                wash_sales.append(
                    WashSaleResponse(
                        tradingsymbol=lot.tradingsymbol,
                        sell_date=sell_dt,
                        sell_price=lot.sell_price or 0.0,
                        rebuy_date=rebuy.traded_at,
                        rebuy_price=rebuy.price,
                        loss_amount=round(abs(lot.realized_pnl or 0.0), 2),
                    )
                )

        return wash_sales

    async def generate_csv(self, fy: str | None = None) -> str:
        """Generate CSV report of tax lots for download."""
        lots = await self.get_lots(fy=fy)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Tradingsymbol",
                "Exchange",
                "Buy Date",
                "Buy Price",
                "Quantity",
                "Remaining Qty",
                "Sell Date",
                "Sell Price",
                "Realized P&L",
                "Holding Type",
            ]
        )

        for lot in lots:
            writer.writerow(
                [
                    lot.tradingsymbol,
                    lot.exchange,
                    lot.buy_date.strftime("%Y-%m-%d") if lot.buy_date else "",
                    lot.buy_price,
                    lot.quantity,
                    lot.remaining_quantity,
                    lot.sell_date.strftime("%Y-%m-%d") if lot.sell_date else "",
                    lot.sell_price if lot.sell_price is not None else "",
                    lot.realized_pnl if lot.realized_pnl is not None else "",
                    lot.holding_type,
                ]
            )

        return output.getvalue()

    def _is_intraday(self, sell_trade: Trade, buy_trades: list[Trade]) -> bool:
        """Determine if a sell trade is intraday."""
        if sell_trade.product == "MIS":
            return True
        if sell_trade.product == "NRML":
            return False
        # CNC: check if bought and sold on the same day
        if sell_trade.product == "CNC" and sell_trade.traded_at:
            sell_date = sell_trade.traded_at.date()
            for bt in buy_trades:
                if bt.tradingsymbol == sell_trade.tradingsymbol and bt.traded_at and bt.traded_at.date() == sell_date:
                    return True
        return False

    def _classify_holding(
        self,
        buy_date: datetime,
        sell_date: datetime | None,
        is_intraday: bool,
        product: str,
    ) -> str:
        """Classify holding type based on trade characteristics."""
        if is_intraday:
            return "INTRADAY"
        if product == "NRML":
            return "FNO"
        if sell_date and buy_date:
            # Normalize both to naive UTC for comparison (SQLite stores naive)
            sd = sell_date.replace(tzinfo=None) if sell_date.tzinfo else sell_date
            bd = buy_date.replace(tzinfo=None) if buy_date.tzinfo else buy_date
            days_held = (sd - bd).days
            return "LTCG" if days_held > 365 else "STCG"
        return "LTCG"

    def _advance_tax_due(self, current_date: date, estimated_annual_tax: float, fy_start: datetime) -> float:
        """Calculate advance tax due by current quarter."""
        fy_year = fy_start.year
        q1_deadline = date(fy_year, 6, 15)
        q2_deadline = date(fy_year, 9, 15)
        q3_deadline = date(fy_year, 12, 15)
        q4_deadline = date(fy_year + 1, 3, 15)

        if current_date <= q1_deadline:
            return estimated_annual_tax * 0.15
        elif current_date <= q2_deadline:
            return estimated_annual_tax * 0.45
        elif current_date <= q3_deadline:
            return estimated_annual_tax * 0.75
        elif current_date <= q4_deadline:
            return estimated_annual_tax * 1.0
        return estimated_annual_tax
