"""Sentiment analysis service — parses Google News RSS for stock sentiment."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}+stock&hl=en-IN&gl=IN&ceid=IN:en"

POSITIVE_WORDS: set[str] = {
    "profit",
    "growth",
    "beat",
    "upgrade",
    "rally",
    "surge",
    "gain",
    "bullish",
    "record",
    "strong",
    "outperform",
    "buy",
    "positive",
    "rise",
    "high",
    "dividend",
    "bonus",
    "expand",
    "recovery",
    "breakout",
}

NEGATIVE_WORDS: set[str] = {
    "loss",
    "downgrade",
    "crash",
    "fraud",
    "miss",
    "decline",
    "fall",
    "bearish",
    "weak",
    "sell",
    "negative",
    "drop",
    "low",
    "debt",
    "default",
    "lawsuit",
    "penalty",
    "warning",
    "concern",
    "risk",
}


class SentimentService:
    """Fetches and analyzes news sentiment for stocks via Google News RSS."""

    async def fetch_sentiment(self, tradingsymbol: str) -> dict[str, Any]:
        """Fetch top headlines and compute sentiment score.

        Returns dict with sentiment_score (-1 to +1), positive/negative counts,
        or available=False.
        """
        try:
            url = GOOGLE_NEWS_RSS.format(query=tradingsymbol)
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return {"available": False}

                return self._parse_rss(resp.text)

        except Exception:
            logger.debug("Failed to fetch sentiment for %s", tradingsymbol)
        return {"available": False}

    @staticmethod
    def _parse_rss(xml_content: str) -> dict[str, Any]:
        """Parse RSS XML and count positive/negative sentiment words."""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return {"available": False}

        titles: list[str] = []
        for item in root.iter("item"):
            title_elem = item.find("title")
            if title_elem is not None and title_elem.text:
                titles.append(title_elem.text)
            if len(titles) >= 5:
                break

        if not titles:
            return {"available": False}

        positive_count = 0
        negative_count = 0
        for title in titles:
            words = title.lower().split()
            for word in words:
                cleaned = word.strip(".,;:!?()[]\"'")
                if cleaned in POSITIVE_WORDS:
                    positive_count += 1
                elif cleaned in NEGATIVE_WORDS:
                    negative_count += 1

        total = positive_count + negative_count
        sentiment_score = 0.0 if total == 0 else (positive_count - negative_count) / total

        return {
            "available": True,
            "sentiment_score": round(sentiment_score, 2),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "headlines_analyzed": len(titles),
            "positive_sentiment": sentiment_score > 0.3,
            "negative_sentiment": sentiment_score < -0.3,
        }
