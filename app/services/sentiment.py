"""Sentiment analysis service — parses Google News RSS for stock sentiment.

Uses FinBERT (ProsusAI/finbert) when transformers+torch are installed,
falls back to keyword matching otherwise.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Try to import FinBERT dependencies
_FINBERT_AVAILABLE = False
try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    _FINBERT_AVAILABLE = True
except ImportError:
    pass

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
    """Fetches and analyzes news sentiment for stocks via Google News RSS.

    Uses FinBERT transformer model when available, keyword matching as fallback.
    """

    _finbert_pipeline: Any = None

    @classmethod
    def _get_finbert_pipeline(cls) -> Any:
        """Lazy-load FinBERT pipeline (heavy — only load once)."""
        if cls._finbert_pipeline is None and _FINBERT_AVAILABLE:
            try:
                model_name = "ProsusAI/finbert"
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModelForSequenceClassification.from_pretrained(model_name)
                cls._finbert_pipeline = pipeline(
                    "sentiment-analysis",
                    model=model,
                    tokenizer=tokenizer,
                    truncation=True,
                    max_length=512,
                )
                logger.info("FinBERT model loaded successfully")
            except Exception:
                logger.warning("Failed to load FinBERT, falling back to keyword matching")
                cls._finbert_pipeline = False  # Mark as failed, don't retry
        return cls._finbert_pipeline if cls._finbert_pipeline is not False else None

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

                titles = self._extract_titles(resp.text)
                if not titles:
                    return {"available": False}

                # Try FinBERT first, fall back to keyword matching
                finbert = self._get_finbert_pipeline()
                if finbert is not None:
                    return await asyncio.to_thread(self._analyze_finbert, titles, finbert)

                return self._analyze_keywords(titles)

        except Exception:
            logger.debug("Failed to fetch sentiment for %s", tradingsymbol)
        return {"available": False}

    @staticmethod
    def _extract_titles(xml_content: str) -> list[str]:
        """Extract headline titles from RSS XML."""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        titles: list[str] = []
        for item in root.iter("item"):
            title_elem = item.find("title")
            if title_elem is not None and title_elem.text:
                titles.append(title_elem.text)
            if len(titles) >= 5:
                break
        return titles

    @staticmethod
    def _analyze_finbert(titles: list[str], finbert_pipeline: Any) -> dict[str, Any]:
        """Analyze sentiment using FinBERT transformer model."""
        results = finbert_pipeline(titles)
        positive_count = 0
        negative_count = 0
        total_score = 0.0

        for result in results:
            label = result["label"].lower()
            score = result["score"]
            if label == "positive":
                positive_count += 1
                total_score += score
            elif label == "negative":
                negative_count += 1
                total_score -= score
            # neutral: no change

        n = len(results)
        sentiment_score = total_score / n if n > 0 else 0.0

        return {
            "available": True,
            "method": "finbert",
            "sentiment_score": round(sentiment_score, 2),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "headlines_analyzed": len(titles),
            "positive_sentiment": sentiment_score > 0.3,
            "negative_sentiment": sentiment_score < -0.3,
        }

    @staticmethod
    def _analyze_keywords(titles: list[str]) -> dict[str, Any]:
        """Analyze sentiment using keyword matching (fallback)."""
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
            "method": "keyword",
            "sentiment_score": round(sentiment_score, 2),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "headlines_analyzed": len(titles),
            "positive_sentiment": sentiment_score > 0.3,
            "negative_sentiment": sentiment_score < -0.3,
        }

    @staticmethod
    def _parse_rss(xml_content: str) -> dict[str, Any]:
        """Parse RSS XML and count positive/negative sentiment words.

        Kept for backward compatibility.
        """
        service = SentimentService()
        titles = service._extract_titles(xml_content)
        if not titles:
            return {"available": False}
        return service._analyze_keywords(titles)
