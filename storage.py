from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class NewsStorage:
    def __init__(self, config: Dict[str, Any]) -> None:
        storage_cfg = config.get("storage", {})
        self.db_path = Path(storage_cfg.get("db_path", "data/news_pipeline.db"))
        self.raw_jsonl_path = Path(storage_cfg.get("raw_jsonl_path", "data/raw_news.jsonl"))
        self.clean_jsonl_path = Path(storage_cfg.get("clean_jsonl_path", "data/clean_news.jsonl"))

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_news (
                    raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    fetch_method TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    content TEXT,
                    published_at TEXT,
                    category TEXT,
                    raw_payload TEXT,
                    is_cleaned INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS clean_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_id INTEGER,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    fetch_method TEXT NOT NULL,
                    published_date TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    cleaned_at TEXT NOT NULL,
                    summary TEXT DEFAULT NULL,
                    summarized_at TEXT DEFAULT NULL,
                    sentiment TEXT DEFAULT NULL,
                    sentiment_score REAL DEFAULT NULL,
                    keywords TEXT DEFAULT NULL,
                    status TEXT DEFAULT 'cleaned'
                );

                CREATE TABLE IF NOT EXISTS insights (
                    insight_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    date_from TEXT,
                    date_to TEXT,
                    category TEXT,
                    article_count INTEGER NOT NULL,
                    trends TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    comparison TEXT NOT NULL,
                    implications TEXT NOT NULL,
                    sentiment_summary TEXT
                );
                """
            )

    def insert_raw_news(self, items: List[Dict[str, Any]]) -> int:
        saved_count = 0
        with self._get_conn() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO raw_news (
                        source_name, fetch_method, fetched_at,
                        title, url, content, published_at, category, raw_payload, is_cleaned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        item.get("source_name", "unknown"),
                        item.get("fetch_method", "unknown"),
                        item.get("fetched_at", datetime.now().isoformat()),
                        item.get("title"),
                        item.get("url"),
                        item.get("content"),
                        item.get("published_at"),
                        item.get("category"),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
                saved_count += 1

        with self.raw_jsonl_path.open("a", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return saved_count

    def get_uncleaned_raw_news(self, include_all: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM raw_news" if include_all else "SELECT * FROM raw_news WHERE is_cleaned = 0"
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(query).fetchall()]

    def mark_raw_cleaned(self, raw_ids: List[int]) -> None:
        if not raw_ids:
            return
        placeholders = ",".join("?" for _ in raw_ids)
        with self._get_conn() as conn:
            conn.execute(f"UPDATE raw_news SET is_cleaned = 1 WHERE raw_id IN ({placeholders})", raw_ids)

    def save_clean_news(self, item: Dict[str, Any], duplicate_policy: str = "skip") -> Tuple[str, Optional[int]]:
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM clean_news WHERE url = ? OR title = ?",
                (item["url"], item["title"]),
            ).fetchone()

            if existing:
                if duplicate_policy.lower() == "upsert":
                    conn.execute(
                        """
                        UPDATE clean_news
                        SET raw_id = ?, title = ?, content = ?, category = ?,
                            source_name = ?, fetch_method = ?, published_date = ?,
                            fetched_at = ?, cleaned_at = ?
                        WHERE id = ?
                        """,
                        (
                            item.get("raw_id"), item["title"], item["content"], item["category"],
                            item["source_name"], item["fetch_method"], item["published_date"],
                            item["fetched_at"], item["cleaned_at"], existing["id"],
                        ),
                    )
                    self._sync_clean_jsonl()
                    return "updated", existing["id"]
                return "skipped", existing["id"]

            cursor = conn.execute(
                """
                INSERT INTO clean_news (
                    raw_id, url, title, content, category,
                    source_name, fetch_method, published_date, fetched_at, cleaned_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cleaned')
                """,
                (
                    item.get("raw_id"), item["url"], item["title"], item["content"],
                    item["category"], item["source_name"], item["fetch_method"],
                    item["published_date"], item["fetched_at"], item["cleaned_at"],
                ),
            )
            new_id = cursor.lastrowid
        self._sync_clean_jsonl()
        return "inserted", new_id

    def _sync_clean_jsonl(self) -> None:
        rows = self.query_clean_news(limit=10000)
        with self.clean_jsonl_path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def get_news_for_summary(
        self, news_id: Optional[int] = None, all_items: bool = False,
        unsummarized_only: bool = True, limit: int = 10, force: bool = False,
    ) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if news_id is not None:
                row = conn.execute("SELECT * FROM clean_news WHERE id = ?", (news_id,)).fetchone()
                return [dict(row)] if row else []
            if unsummarized_only or not force:
                rows = conn.execute(
                    "SELECT * FROM clean_news WHERE summary IS NULL OR summary = '' ORDER BY id ASC LIMIT ?",
                    (limit if not all_items else 10000,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM clean_news ORDER BY id ASC LIMIT ?",
                    (limit if not all_items else 10000,),
                ).fetchall()
            return [dict(r) for r in rows]

    def update_summary_and_sentiment(
        self, news_id: int, summary: str, sentiment: str, sentiment_score: float, keywords: str
    ) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE clean_news
                SET summary = ?, summarized_at = ?, sentiment = ?,
                    sentiment_score = ?, keywords = ?, status = 'summarized'
                WHERE id = ?
                """,
                (summary, now_str, sentiment, sentiment_score, keywords, news_id),
            )
        self._sync_clean_jsonl()

    def query_clean_news(
        self, category: Optional[str] = None, date_from: Optional[str] = None,
        date_to: Optional[str] = None, keyword: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clauses = ["1=1"]
        params: List[Any] = []
        if category:
            clauses.append("category LIKE ?")
            params.append(f"%{category}%")
        if date_from:
            clauses.append("published_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("published_date <= ?")
            params.append(date_to)
        if keyword:
            clauses.append("(title LIKE ? OR content LIKE ? OR IFNULL(summary, '') LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        if status in ("summarized", "cleaned"):
            clauses.append("status = ?")
            params.append(status)

        sql = f"SELECT * FROM clean_news WHERE {' AND '.join(clauses)} ORDER BY published_date DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM clean_news WHERE id = ?", (news_id,)).fetchone()
            return dict(row) if row else None

    def save_insight(self, insight_data: Dict[str, Any]) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO insights (
                    created_at, date_from, date_to, category, article_count,
                    trends, keywords, comparison, implications, sentiment_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    insight_data.get("date_from") or "전체",
                    insight_data.get("date_to") or "전체",
                    insight_data.get("category") or "전체",
                    insight_data.get("article_count", 0),
                    json.dumps(insight_data.get("trends", []), ensure_ascii=False),
                    json.dumps(insight_data.get("keywords", []), ensure_ascii=False),
                    json.dumps(insight_data.get("comparison", {}), ensure_ascii=False),
                    insight_data.get("implications", ""),
                    json.dumps(insight_data.get("sentiment_summary", {}), ensure_ascii=False),
                ),
            )
            return cursor.lastrowid or 0

    def get_latest_insight(self, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM insights ORDER BY insight_id DESC LIMIT 1").fetchone()
            if not row:
                return None
            d = dict(row)
            d["trends"] = json.loads(d["trends"])
            d["keywords"] = json.loads(d["keywords"])
            d["comparison"] = json.loads(d["comparison"])
            d["sentiment_summary"] = json.loads(d["sentiment_summary"] or "{}")
            return d

    def get_pipeline_metrics(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            raw_total = conn.execute("SELECT COUNT(*) FROM raw_news").fetchone()[0]
            clean_total = conn.execute("SELECT COUNT(*) FROM clean_news").fetchone()[0]
            summarized_total = conn.execute(
                "SELECT COUNT(*) FROM clean_news WHERE summary IS NOT NULL AND summary != ''"
            ).fetchone()[0]
            avg_lengths = conn.execute(
                "SELECT AVG(LENGTH(content)) as avg_c, AVG(LENGTH(summary)) as avg_s FROM clean_news"
            ).fetchone()
            cat_rows = conn.execute("SELECT category, COUNT(*) as cnt FROM clean_news GROUP BY category ORDER BY cnt DESC").fetchall()
            date_rows = conn.execute("SELECT published_date, COUNT(*) as cnt FROM clean_news GROUP BY published_date ORDER BY published_date ASC").fetchall()
            sent_rows = conn.execute("SELECT IFNULL(sentiment, '미분석') as sentiment, COUNT(*) as cnt FROM clean_news GROUP BY IFNULL(sentiment, '미분석')").fetchall()

        clean_rate = (clean_total / raw_total * 100.0) if raw_total > 0 else 0.0
        summary_rate = (summarized_total / clean_total * 100.0) if clean_total > 0 else 0.0
        avg_c = float(avg_lengths["avg_c"] or 0.0)
        avg_s = float(avg_lengths["avg_s"] or 0.0)
        comp_ratio = ((1.0 - (avg_s / avg_c)) * 100.0) if (avg_c > 0 and avg_s > 0) else 0.0

        return {
            "raw_total": raw_total,
            "clean_total": clean_total,
            "summarized_total": summarized_total,
            "clean_rate_pct": round(clean_rate, 1),
            "summary_coverage_pct": round(summary_rate, 1),
            "avg_content_len": round(avg_c, 1),
            "avg_summary_len": round(avg_s, 1),
            "compression_ratio_pct": round(comp_ratio, 1),
            "by_category": [dict(r) for r in cat_rows],
            "by_date": [dict(r) for r in date_rows],
            "by_sentiment": [dict(r) for r in sent_rows],
        }