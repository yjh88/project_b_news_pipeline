from __future__ import annotations
import html
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger("news_pipeline")


class NewsCleaner:
    def __init__(self, config: Dict[str, Any]) -> None:
        cleaner_cfg = config.get("cleaner", {})
        self.duplicate_policy = cleaner_cfg.get("duplicate_policy", "upsert")
        self.default_category = cleaner_cfg.get("default_category", "일반")
        self.min_content_length = int(cleaner_cfg.get("min_content_length", 20))

    @staticmethod
    def normalize_text(text: Optional[str]) -> str:
        if not text:
            return ""
        unescaped = html.unescape(str(text))
        if "<" in unescaped and ">" in unescaped:
            unescaped = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
        cleaned = re.sub(r"[\r\n\t]+", " ", unescaped)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def normalize_date(date_str: Optional[str], fallback_date: Optional[str] = None) -> str:
        raw = (date_str or "").strip()
        if not raw:
            if fallback_date and len(fallback_date) >= 10:
                return fallback_date[:10]
            return datetime.now().strftime("%Y-%m-%d")

        match = re.search(r"(\d{4})[-./년\s](\d{1,2})[-./월\s](\d{1,2})", raw)
        if match:
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{y:04d}-{m:02d}-{d:02d}"

        try:
            dt = parsedate_to_datetime(raw)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        return datetime.now().strftime("%Y-%m-%d")

    def clean_item(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = self.normalize_text(raw_item.get("title"))
        url = (raw_item.get("url") or "").strip()
        content = self.normalize_text(raw_item.get("content"))

        if not title or not url or not content:
            logger.warning(
                f"필수 필드 누락으로 정제 제외 (raw_id={raw_item.get('raw_id')}): title='{title[:15]}', url='{url}'"
            )
            return None

        if len(content) < self.min_content_length:
            logger.warning(
                f"본문 길이 미달({len(content)}자 < {self.min_content_length}자)로 정제 제외: title='{title[:20]}'"
            )
            return None

        category = self.normalize_text(raw_item.get("category")) or self.default_category
        source_name = self.normalize_text(raw_item.get("source_name")) or "unknown"
        fetch_method = self.normalize_text(raw_item.get("fetch_method")) or "unknown"
        fetched_at = raw_item.get("fetched_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        published_date = self.normalize_date(raw_item.get("published_at"), fallback_date=fetched_at)

        return {
            "raw_id": raw_item.get("raw_id"),
            "url": url,
            "title": title,
            "content": content,
            "category": category,
            "source_name": source_name,
            "fetch_method": fetch_method,
            "published_date": published_date,
            "fetched_at": fetched_at,
            "cleaned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def process_batch(
        self,
        raw_items: List[Dict[str, Any]],
        storage: Any,
        policy_override: Optional[str] = None,
    ) -> Dict[str, int]:
        policy = policy_override or self.duplicate_policy
        stats = {
            "total_raw": len(raw_items),
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "invalid": 0,
        }
        processed_raw_ids: List[int] = []

        for raw in raw_items:
            if raw.get("raw_id") is not None:
                processed_raw_ids.append(int(raw["raw_id"]))

            cleaned = self.clean_item(raw)
            if cleaned is None:
                stats["invalid"] += 1
                continue

            status, _ = storage.save_clean_news(cleaned, duplicate_policy=policy)
            if status in stats:
                stats[status] += 1

        storage.mark_raw_cleaned(processed_raw_ids)
        logger.info(
            f"데이터 정제 완료 (정책={policy}): 신규={stats['inserted']}건, "
            f"업데이트(upsert)={stats['updated']}건, 중복스킵={stats['skipped']}건, "
            f"유효성탈락={stats['invalid']}건"
        )
        return stats