from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal_entry import JournalEntry
from app.schemas.journal import (
    JournalAnalytics,
    JournalEntryResponse,
    StrategyStats,
    TagStats,
)


class JournalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_entry(
        self,
        tradingsymbol: str,
        entry_type: str,
        content: str = "",
        tags: str = "",
        strategy: str = "",
        outcome: str = "",
        emotional_state: str = "",
        trade_id: int | None = None,
    ) -> JournalEntry:
        entry = JournalEntry(
            tradingsymbol=tradingsymbol,
            entry_type=entry_type,
            content=content,
            tags=tags,
            strategy=strategy,
            outcome=outcome,
            emotional_state=emotional_state,
            trade_id=trade_id,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_entry(self, entry_id: int) -> JournalEntry | None:
        result = await self.db.execute(select(JournalEntry).where(JournalEntry.id == entry_id))
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        tradingsymbol: str | None = None,
        entry_type: str | None = None,
        trade_id: int | None = None,
    ) -> list[JournalEntryResponse]:
        query = select(JournalEntry).order_by(JournalEntry.created_at.desc())
        if tradingsymbol is not None:
            query = query.where(JournalEntry.tradingsymbol == tradingsymbol)
        if entry_type is not None:
            query = query.where(JournalEntry.entry_type == entry_type)
        if trade_id is not None:
            query = query.where(JournalEntry.trade_id == trade_id)
        result = await self.db.execute(query)
        entries = list(result.scalars().all())
        return [JournalEntryResponse.model_validate(e) for e in entries]

    async def update_entry(
        self,
        entry_id: int,
        tradingsymbol: str | None = None,
        entry_type: str | None = None,
        content: str | None = None,
        tags: str | None = None,
        strategy: str | None = None,
        outcome: str | None = None,
        emotional_state: str | None = None,
        trade_id: int | None = None,
    ) -> JournalEntry | None:
        result = await self.db.execute(select(JournalEntry).where(JournalEntry.id == entry_id))
        entry = result.scalar_one_or_none()
        if entry is None:
            return None

        if tradingsymbol is not None:
            entry.tradingsymbol = tradingsymbol
        if entry_type is not None:
            entry.entry_type = entry_type
        if content is not None:
            entry.content = content
        if tags is not None:
            entry.tags = tags
        if strategy is not None:
            entry.strategy = strategy
        if outcome is not None:
            entry.outcome = outcome
        if emotional_state is not None:
            entry.emotional_state = emotional_state
        if trade_id is not None:
            entry.trade_id = trade_id

        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete_entry(self, entry_id: int) -> bool:
        result = await self.db.execute(select(JournalEntry).where(JournalEntry.id == entry_id))
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await self.db.delete(entry)
        await self.db.commit()
        return True

    async def get_analytics(self) -> JournalAnalytics:
        result = await self.db.execute(select(JournalEntry))
        entries = list(result.scalars().all())

        total = len(entries)
        wins = sum(1 for e in entries if e.outcome == "win")
        losses = sum(1 for e in entries if e.outcome == "loss")
        breakeven = sum(1 for e in entries if e.outcome == "breakeven")
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

        # By strategy
        strategy_groups: dict[str, list[JournalEntry]] = {}
        for e in entries:
            if e.strategy:
                strategy_groups.setdefault(e.strategy, []).append(e)

        by_strategy = []
        for strat, group in strategy_groups.items():
            s_wins = sum(1 for e in group if e.outcome == "win")
            s_losses = sum(1 for e in group if e.outcome == "loss")
            s_wr = (s_wins / (s_wins + s_losses) * 100) if (s_wins + s_losses) > 0 else 0.0
            by_strategy.append(
                StrategyStats(
                    strategy=strat,
                    count=len(group),
                    wins=s_wins,
                    losses=s_losses,
                    win_rate=s_wr,
                )
            )

        # By tag
        tag_counter: Counter[str] = Counter()
        for e in entries:
            if e.tags:
                for tag in e.tags.split(","):
                    tag = tag.strip()
                    if tag:
                        tag_counter[tag] += 1

        by_tag = [TagStats(tag=t, count=c) for t, c in tag_counter.most_common()]

        return JournalAnalytics(
            total_entries=total,
            win_rate=win_rate,
            total_wins=wins,
            total_losses=losses,
            total_breakeven=breakeven,
            by_strategy=by_strategy,
            by_tag=by_tag,
        )
