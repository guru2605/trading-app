from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.holding import Holding
from app.schemas.portfolio import CorrelationPair, CorrelationResponse
from app.services.market_data import MarketDataService

CORRELATION_THRESHOLD = 0.7
CONCENTRATION_THRESHOLD = 0.8


class CorrelationService:
    def __init__(self, db: AsyncSession, kite: KiteClient | None = None) -> None:
        self.db = db
        self.kite = kite
        self.market_data = MarketDataService()

    async def compute_correlation(self, days: int = 90) -> CorrelationResponse:
        """Compute Pearson correlation matrix for portfolio holdings using 90-day historical data."""
        # Get active holdings
        result = await self.db.execute(select(Holding).where(Holding.quantity > 0))
        holdings = list(result.scalars().all())

        if len(holdings) < 2:
            symbols = [h.tradingsymbol for h in holdings]
            return CorrelationResponse(
                symbols=symbols,
                matrix=[[1.0]] if holdings else [],
                high_correlations=[],
                warnings=["Need at least 2 holdings to compute correlations."],
            )

        symbols = [h.tradingsymbol for h in holdings]
        exchanges = {h.tradingsymbol: h.exchange for h in holdings}

        # Fetch historical close prices via yfinance
        to_date = datetime.now(UTC)
        from_date = to_date - timedelta(days=days)
        price_series: dict[str, list[float]] = {}

        for symbol in symbols:
            exchange = exchanges.get(symbol, "NSE")
            try:
                candles = await self.market_data.fetch_historical(symbol, exchange, from_date, to_date, "day")
                price_series[symbol] = [c["close"] for c in candles if "close" in c]
            except Exception:
                continue

        # Filter to symbols with enough data
        valid_symbols = [s for s in symbols if s in price_series and len(price_series[s]) >= 10]

        if len(valid_symbols) < 2:
            return CorrelationResponse(
                symbols=valid_symbols,
                matrix=[[1.0]] if valid_symbols else [],
                high_correlations=[],
                warnings=["Insufficient historical data for correlation analysis."],
            )

        # Align series to minimum length
        min_len = min(len(price_series[s]) for s in valid_symbols)
        aligned = np.array([price_series[s][:min_len] for s in valid_symbols])

        # Compute daily returns
        returns = np.diff(aligned, axis=1) / aligned[:, :-1]

        # Handle zero-variance (constant price) series
        std = np.std(returns, axis=1)
        if np.any(std == 0):
            warnings = ["Some holdings have zero price variance; correlation may be unreliable."]
        else:
            warnings = []

        # Compute Pearson correlation matrix
        corr_matrix = np.corrcoef(returns)
        # Replace NaN with 0 (from zero-variance series)
        corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
        matrix = [
            [round(float(corr_matrix[i][j]), 4) for j in range(len(valid_symbols))] for i in range(len(valid_symbols))
        ]

        # Find high correlations
        high_correlations: list[CorrelationPair] = []
        for i in range(len(valid_symbols)):
            for j in range(i + 1, len(valid_symbols)):
                corr = float(corr_matrix[i][j])
                if abs(corr) >= CORRELATION_THRESHOLD:
                    high_correlations.append(
                        CorrelationPair(
                            stock_a=valid_symbols[i],
                            stock_b=valid_symbols[j],
                            correlation=round(corr, 4),
                        )
                    )

        # Concentration warnings
        if high_correlations:
            warnings.append(f"{len(high_correlations)} pair(s) exceed {CORRELATION_THRESHOLD} correlation threshold.")

        # Check if any group of highly correlated stocks dominates
        holding_values = {h.tradingsymbol: h.last_price * h.quantity for h in holdings}
        total_value = sum(holding_values.values())
        if total_value > 0:
            for pair in high_correlations:
                combined_weight = (
                    holding_values.get(pair.stock_a, 0) + holding_values.get(pair.stock_b, 0)
                ) / total_value
                if combined_weight >= CONCENTRATION_THRESHOLD:
                    warnings.append(
                        f"{pair.stock_a} + {pair.stock_b} represent "
                        f"{combined_weight:.0%} of portfolio with {pair.correlation:.2f} correlation."
                    )

        return CorrelationResponse(
            symbols=valid_symbols,
            matrix=matrix,
            high_correlations=sorted(high_correlations, key=lambda p: abs(p.correlation), reverse=True),
            warnings=warnings,
        )
