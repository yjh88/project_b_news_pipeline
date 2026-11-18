from __future__ import annotations
import csv
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from ai_service import AIService

logger = logging.getLogger("news_pipeline")


class ReportGenerator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.output_dir = Path(config.get("storage", {}).get("output_dir", "output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.top_n = int(config.get("report", {}).get("top_n", 5))

    def generate_report(
        self,
        storage: Any,
        chart_paths: Dict[str, str],
        top_n: Optional[int] = None,
        report_format: str = "both",
    ) -> Dict[str, str]:
        n = top_n or self.top_n
        metrics = storage.get_pipeline_metrics()
        articles = storage.query_clean_news(limit=1000)
        insight = storage.get_latest_insight()

        all_texts = [f"{a.get('title', '')} {a.get('content', '')}" for a in articles]
        raw_keywords = AIService.extract_keywords_from_texts(all_texts, top_k=n * 2)
        kw_counter: Counter[str] = Counter()
        for text in all_texts:
            for kw in raw_keywords:
                if kw in text:
                    kw_counter[kw] += 1
        top_keywords = kw_counter.most_common(n)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_lines = [
            "# [Project B] AI 뉴스 트렌드 및 종합 분석 리포트",
            f"- 생성 일시: {now_str}",
            f"- 분석 대상: 총 {metrics['clean_total']}건 (원본 수집 {metrics['raw_total']}건)",
            "",
            "## 1. 데이터 파이프라인 품질 지표 (Quality Metrics)",
            "| 지표명 | 측정값 | 설명 |",
            "| :--- | :---: | :--- |",
            f"| 데이터 정제 유효율 (Clean Rate) | {metrics['clean_rate_pct']}% ({metrics['clean_total']}/{metrics['raw_total']}건) | 원본 수집 대비 필수필드 검증 및 중복 제거 후 유효 비율 |",
            f"| AI 요약 완료율 (Summary Coverage) | {metrics['summary_coverage_pct']}% ({metrics['summarized_total']}/{metrics['clean_total']}건) | 정제 데이터 중 AI 요약 및 감성 분석이 완료된 비율 |",
            f"| 본문 대비 요약 압축률 (Compression Ratio) | {metrics['compression_ratio_pct']}% | 평균 본문({metrics['avg_content_len']}자) → 평균 요약({metrics['avg_summary_len']}자) 축약률 |",
            "",
            f"## 2. TOP {n} 핵심 키워드 및 카테고리 집계",
            f"### 2.1 핵심 키워드 TOP {n} (문서 출현 빈도 기준)",
            "| 순위 | 키워드 | 출현 기사 수 | 비중(%) |",
            "| :---: | :--- | :---: | :---: |",
        ]

        total_art = max(metrics["clean_total"], 1)
        for rank, (kw, cnt) in enumerate(top_keywords, start=1):
            pct = round(cnt / total_art * 100, 1)
            md_lines.append(f"| {rank}위 | **{kw}** | {cnt}건 | {pct}% |")

        md_lines.extend(
            [
                "",
                "### 2.2 카테고리별 분포",
                "| 카테고리 | 뉴스 건수 | 점유율(%) |",
                "| :--- | :---: | :---: |",
            ]
        )
        for row in metrics["by_category"][:n]:
            pct = round(row["cnt"] / total_art * 100, 1)
            md_lines.append(f"| {row['category']} | {row['cnt']}건 | {pct}% |")

        md_lines.extend(
            [
                "",
                "### 2.3 감성 분석(Sentiment Analysis) 집계",
                "| 감성 분류 | 뉴스 건수 | 비중(%) |",
                "| :--- | :---: | :---: |",
            ]
        )
        for row in metrics["by_sentiment"]:
            pct = round(row["cnt"] / total_art * 100, 1)
            md_lines.append(f"| {row['sentiment']} | {row['cnt']}건 | {pct}% |")

        md_lines.append("")
        md_lines.append("## 3. AI 종합 인사이트 분석 결과")
        if insight:
            md_lines.append(
                f"- 분석 범위: 기간({insight.get('date_from')} ~ {insight.get('date_to')}), "
                f"카테고리({insight.get('category')}), 대상({insight.get('article_count')}건)"
            )
            md_lines.append("\n### [주요 트렌드]")
            for t in insight.get("trends", []):
                md_lines.append(f"- {t}")

            md_lines.append("\n### [핵심 키워드]")
            md_lines.append("- " + ", ".join(insight.get("keywords", [])))

            comp = insight.get("comparison", {})
            md_lines.append("\n### [섹터별 공통점 및 차이점]")
            md_lines.append(f"- **공통점**: {comp.get('공통점', '-')}")
            md_lines.append(f"- **차이점**: {comp.get('차이점', '-')}")

            md_lines.append("\n### [종합 시사점]")
            md_lines.append(f"{insight.get('implications', '')}")
        else:
            md_lines.append("- 저장된 AI 인사이트 분석 결과가 없습니다.")

        md_lines.extend(
            [
                "",
                "## 4. 주요 뉴스 AI 요약 목록 (최신순)",
                "| ID | 발행일 | 카테고리 | 감성 | 제목 | AI 요약 |",
                "| :---: | :---: | :---: | :---: | :--- | :--- |",
            ]
        )
        for art in articles[:10]:
            summary_txt = art.get("summary") or "(미요약)"
            sent_txt = art.get("sentiment") or "-"
            md_lines.append(
                f"| {art['id']} | {art['published_date']} | {art['category']} | {sent_txt} | {art['title']} | {summary_txt} |"
            )

        md_lines.extend(
            [
                "",
                "## 5. 생성된 시각화 차트 파일",
                f"- 카테고리별 뉴스 수 차트: `{chart_paths.get('category_chart', '')}`",
                f"- 일자별 수집 추이 차트: `{chart_paths.get('daily_trend_chart', '')}`",
                f"- 감성 분석 분포 차트: `{chart_paths.get('sentiment_chart', '')}`",
                f"- 종합 대시보드 차트: `{chart_paths.get('overview_dashboard', '')}`",
            ]
        )

        report_content = "\n".join(md_lines)
        saved_files: Dict[str, str] = {}

        if report_format in ("md", "both"):
            md_path = self.output_dir / "insight_report.md"
            md_path.write_text(report_content, encoding="utf-8")
            saved_files["md"] = str(md_path)
            logger.info(f"마크다운 리포트 생성 완료: {md_path}")

        if report_format in ("txt", "both"):
            txt_path = self.output_dir / "insight_report.txt"
            txt_path.write_text(report_content, encoding="utf-8")
            saved_files["txt"] = str(txt_path)
            logger.info(f"텍스트 리포트 생성 완료: {txt_path}")

        print("\n" + "=" * 70)
        print(report_content)
        print("=" * 70 + "\n")
        return saved_files

    def export_data(
        self,
        storage: Any,
        export_format: str = "all",
        status_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ) -> List[str]:
        rows = storage.query_clean_news(
            category=category_filter,
            status=status_filter,
            limit=10000,
        )
        exported_paths: List[str] = []
        suffix = f"_{status_filter}" if status_filter else ""
        formats = ["csv", "jsonl", "xlsx"] if export_format.lower() == "all" else [export_format.lower()]

        for fmt in formats:
            if fmt == "csv":
                csv_path = self.output_dir / f"news_export{suffix}.csv"
                fieldnames = [
                    "id", "published_date", "category", "source_name", "fetch_method",
                    "title", "summary", "sentiment", "sentiment_score", "keywords", "status", "url",
                ]
                with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                exported_paths.append(str(csv_path))
                logger.info(f"CSV 내보내기 완료 ({len(rows)}건): {csv_path}")

            elif fmt == "jsonl":
                jsonl_path = self.output_dir / f"news_export{suffix}.jsonl"
                with jsonl_path.open("w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                exported_paths.append(str(jsonl_path))
                logger.info(f"JSONL 내보내기 완료 ({len(rows)}건): {jsonl_path}")

            elif fmt in ("excel", "xlsx"):
                xlsx_path = self.output_dir / f"news_export{suffix}.xlsx"
                df = pd.DataFrame(rows)
                if not df.empty:
                    cols = [
                        "id", "published_date", "category", "source_name", "fetch_method",
                        "title", "summary", "sentiment", "sentiment_score", "keywords", "status", "url", "content",
                    ]
                    df = df[[c for c in cols if c in df.columns]]
                df.to_excel(xlsx_path, index=False, engine="openpyxl")
                exported_paths.append(str(xlsx_path))
                logger.info(f"Excel(.xlsx) 내보내기 완료 ({len(rows)}건): {xlsx_path}")

        return exported_paths