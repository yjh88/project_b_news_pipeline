from __future__ import annotations
import argparse
import sys
from typing import Any, Dict

from ai_service import AIService
from cleaner import NewsCleaner
from config_loader import load_config, setup_logging
from fetcher import NewsFetcher
from reporter import ReportGenerator
from storage import NewsStorage
from visualizer import NewsVisualizer


def handle_fetch(args: argparse.Namespace, config: Dict[str, Any], storage: NewsStorage) -> None:
    logger = setup_logging()
    fetcher = NewsFetcher(config)
    items = fetcher.fetch(
        source=args.source,
        limit=args.limit,
        category_override=args.category,
    )
    saved = storage.insert_raw_news(items)
    logger.info(f"raw 저장소에 저장 완료 ({saved}건)")


def handle_clean(args: argparse.Namespace, config: Dict[str, Any], storage: NewsStorage) -> None:
    logger = setup_logging()
    cleaner = NewsCleaner(config)
    raw_items = storage.get_uncleaned_raw_news(include_all=args.all)
    if not raw_items:
        logger.info("정제할 신규 raw 데이터가 없습니다. (--all 옵션으로 전체 재정제 가능)")
        return
    cleaner.process_batch(raw_items, storage=storage, policy_override=args.policy)


def handle_summarize(args: argparse.Namespace, config: Dict[str, Any], storage: NewsStorage) -> None:
    logger = setup_logging()
    ai = AIService(config)
    targets = storage.get_news_for_summary(
        news_id=args.id,
        all_items=args.all,
        unsummarized_only=args.unsummarized or not args.force,
        limit=args.limit,
        force=args.force,
    )
    total = len(targets)
    logger.info(f"요약 대상: {total}건")
    if total == 0:
        logger.info("요약할 대상 뉴스가 없습니다. (이미 요약된 뉴스는 기본 스킵 처리됩니다)")
        return

    success_cnt = 0
    fail_cnt = 0
    for idx, item in enumerate(targets, start=1):
        nid = item["id"]
        if item.get("summary") and not args.force and args.id is None:
            logger.info(f"[{idx}/{total}] ID={nid} 이미 요약됨 → 스킵")
            continue
        try:
            summary, sentiment, score, keywords = ai.summarize_and_analyze_article(
                item["title"], item["content"]
            )
            storage.update_summary_and_sentiment(
                news_id=nid,
                summary=summary,
                sentiment=sentiment,
                sentiment_score=score,
                keywords=", ".join(keywords),
            )
            orig_len = len(item["content"])
            sum_len = len(summary)
            logger.info(
                f"[{idx}/{total}] ID={nid} 요약 완료 ({orig_len}자 → {sum_len}자, 감성={sentiment})"
            )
            success_cnt += 1
        except Exception as exc:
            logger.error(f"[{idx}/{total}] ID={nid} 요약 실패 (스킵 처리): {exc}")
            fail_cnt += 1

    logger.info(f"요약 완료: {success_cnt}건 성공, {fail_cnt}건 실패")


def handle_analyze(args: argparse.Namespace, config: Dict[str, Any], storage: NewsStorage) -> None:
    logger = setup_logging()
    ai = AIService(config)
    articles = storage.query_clean_news(
        category=args.category,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
    )
    logger.info(f"분석 대상: {len(articles)}건")
    insight = ai.analyze_insights(
        articles=articles,
        date_from=args.date_from,
        date_to=args.date_to,
        category=args.category,
    )
    storage.save_insight(insight)

    print("\n=== AI 인사이트 분석 결과 ===")
    print("[주요 트렌드]")
    for t in insight.get("trends", []):
        print(f"- {t}\n")

    print("[핵심 키워드]")
    print(", ".join(insight.get("keywords", [])) + "\n")

    comp = insight.get("comparison", {})
    print("[공통점 및 차이점]")
    print(f"- 공통점: {comp.get('공통점', '-')}")
    print(f"- 차이점: {comp.get('차이점', '-')}\n")

    print("[감성 분포 요약]")
    sent_map = insight.get("sentiment_summary", {})
    print(
        f"긍정: {sent_map.get('긍정', 0)}건 | 중립: {sent_map.get('중립', 0)}건 | 부정: {sent_map.get('부정', 0)}건\n"
    )

    print("[시사점]")
    print(insight.get("implications", ""))
    print("==============================\n")


def handle_report(args: argparse.Namespace, config: Dict[str, Any], storage: NewsStorage) -> None:
    out_dir = config.get("storage", {}).get("output_dir", "output")
    visualizer = NewsVisualizer(output_dir=out_dir)
    metrics = storage.get_pipeline_metrics()
    chart_paths = visualizer.generate_all_charts(metrics)

    reporter = ReportGenerator(config)
    reporter.generate_report(
        storage=storage,
        chart_paths=chart_paths,
        top_n=args.top_n,
        report_format=args.format,
    )


def handle_export(args: argparse.Namespace, config: Dict[str, Any], storage: NewsStorage) -> None:
    reporter = ReportGenerator(config)
    reporter.export_data(
        storage=storage,
        export_format=args.format,
        status_filter=args.status,
        category_filter=args.category,
    )


def handle_list(args: argparse.Namespace, storage: NewsStorage) -> None:
    offset = (max(args.page, 1) - 1) * args.page_size
    rows = storage.query_clean_news(
        category=args.category,
        date_from=args.date,
        date_to=args.date,
        keyword=args.keyword,
        status=args.status,
        limit=args.page_size,
        offset=offset,
    )
    print(
        f"\n=== 뉴스 목록 조회 (페이지={args.page}, 페이지당={args.page_size}건, 조회결과={len(rows)}건) ==="
    )
    if not rows:
        print("조건에 해당하는 뉴스가 없습니다.")
        return
    print(f"{'ID':<4} | {'발행일':<10} | {'카테고리':<8} | {'감성':<4} | {'상태':<10} | 제목")
    print("-" * 85)
    for r in rows:
        print(
            f"{r['id']:<4} | {r['published_date']:<10} | {r['category']:<8} | "
            f"{(r.get('sentiment') or '-'):<4} | {r['status']:<10} | {r['title'][:42]}"
        )
    print()


def handle_show(args: argparse.Namespace, storage: NewsStorage) -> None:
    row = storage.get_news_by_id(args.id)
    if not row:
        print(f"[WARNING] ID={args.id} 에 해당하는 뉴스를 찾을 수 없습니다.")
        return
    print("\n" + "=" * 70)
    print(f"[뉴스 상세 조회] ID = {row['id']}")
    print("=" * 70)
    print(f"- 제목       : {row['title']}")
    print(f"- 카테고리   : {row['category']}")
    print(f"- 발행일     : {row['published_date']}")
    print(f"- 출처/방식  : {row['source_name']} ({row['fetch_method']})")
    print(f"- 원본 URL   : {row['url']}")
    print(f"- 처리 상태  : {row['status']}")
    print(f"- 감성 분석  : {row.get('sentiment') or '미분석'} (점수: {row.get('sentiment_score')})")
    print(f"- 핵심 키워드: {row.get('keywords') or '-'}")
    print("-" * 70)
    print(f"[본문]\n{row['content']}")
    print("-" * 70)
    print(f"[AI 요약]\n{row.get('summary') or '아직 요약되지 않았습니다.'}")
    print("=" * 70 + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="news_pipeline",
        description="[Project B] AI 뉴스 트렌드 및 종합 분석 리포트 CLI 애플리케이션",
    )
    parser.add_argument(
        "--config", default="config.json", help="설정 파일 경로 (기본값: config.json)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="실행할 서브커맨드")

    p_fetch = subparsers.add_parser("fetch", help="외부 API/RSS 및 크롤링으로 뉴스 데이터 수집")
    p_fetch.add_argument("--source", default="all", help="뉴스 소스 지정 (all | naver | yonhap_rss | google_rss | sample)")
    p_fetch.add_argument("--limit", type=int, default=20, help="최대 수집 건수 (기본: 20)")
    p_fetch.add_argument("--category", default=None, help="카테고리 수동 지정 옵션")

    p_clean = subparsers.add_parser("clean", help="수집된 raw 데이터 정제 및 중복 처리")
    p_clean.add_argument("--policy", choices=["skip", "upsert"], default=None, help="중복 뉴스 처리 정책")
    p_clean.add_argument("--all", action="store_true", help="이미 정제된 raw 데이터도 포함하여 재정제")

    p_sum = subparsers.add_parser("summarize", help="AI API를 호출하여 뉴스 본문 요약 및 감성 분석")
    p_sum.add_argument("--all", action="store_true", help="전체 뉴스를 대상으로 요약")
    p_sum.add_argument("--id", type=int, default=None, help="특정 뉴스 ID만 요약")
    p_sum.add_argument("--unsummarized", action="store_true", help="아직 요약되지 않은 뉴스만 요약")
    p_sum.add_argument("--limit", type=int, default=10, help="최대 요약 건수 (기본: 10)")
    p_sum.add_argument("--force", action="store_true", help="이미 요약된 뉴스도 강제 재요약")

    p_ana = subparsers.add_parser("analyze", help="기간 및 카테고리별 AI 인사이트 종합 분석")
    p_ana.add_argument("--date-from", dest="date_from", default=None, help="시작일 (YYYY-MM-DD)")
    p_ana.add_argument("--date-to", dest="date_to", default=None, help="종료일 (YYYY-MM-DD)")
    p_ana.add_argument("--category", default=None, help="분석할 카테고리 필터")
    p_ana.add_argument("--limit", type=int, default=50, help="최대 분석 기사 수")

    p_rep = subparsers.add_parser("report", help="시각화 차트(PNG) 및 종합 리포트(MD/TXT) 생성")
    p_rep.add_argument("--format", choices=["md", "txt", "both"], default="both", help="리포트 저장 파일 포맷")
    p_rep.add_argument("--top-n", dest="top_n", type=int, default=5, help="TOP N 집계 개수")

    p_exp = subparsers.add_parser("export", help="정제/요약된 뉴스를 CSV, JSONL, Excel로 내보내기")
    p_exp.add_argument("--format", choices=["csv", "jsonl", "xlsx", "excel", "all"], default="all", help="내보낼 파일 포맷")
    p_exp.add_argument("--status", choices=["summarized", "cleaned"], default=None, help="상태 필터링")
    p_exp.add_argument("--category", default=None, help="카테고리 필터링")

    p_list = subparsers.add_parser("list", help="[보너스] 저장된 뉴스 목록 조회 (필터링/페이지네이션)")
    p_list.add_argument("--category", default=None, help="카테고리 필터")
    p_list.add_argument("--date", default=None, help="특정 발행일 필터 (YYYY-MM-DD)")
    p_list.add_argument("--keyword", default=None, help="제목/본문/요약 키워드 검색")
    p_list.add_argument("--status", choices=["summarized", "cleaned"], default=None, help="상태 필터")
    p_list.add_argument("--page", type=int, default=1, help="페이지 번호")
    p_list.add_argument("--page-size", dest="page_size", type=int, default=10, help="페이지당 출력 건수")

    p_show = subparsers.add_parser("show", help="[보너스] 특정 뉴스 상세 정보 및 요약 조회")
    p_show.add_argument("--id", type=int, required=True, help="조회할 뉴스 ID")

    p_pipe = subparsers.add_parser("pipeline", help="수집→정제→AI요약→인사이트분석→리포트→내보내기 일괄 실행")
    p_pipe.add_argument("--source", default="sample", help="수집 소스")
    p_pipe.add_argument("--limit", type=int, default=20, help="수집 및 요약 건수")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging()
    config = load_config(args.config)
    storage = NewsStorage(config)

    if args.command == "fetch":
        handle_fetch(args, config, storage)
    elif args.command == "clean":
        handle_clean(args, config, storage)
    elif args.command == "summarize":
        handle_summarize(args, config, storage)
    elif args.command == "analyze":
        handle_analyze(args, config, storage)
    elif args.command == "report":
        handle_report(args, config, storage)
    elif args.command == "export":
        handle_export(args, config, storage)
    elif args.command == "list":
        handle_list(args, storage)
    elif args.command == "show":
        handle_show(args, storage)
    elif args.command == "pipeline":
        handle_fetch(argparse.Namespace(source=args.source, limit=args.limit, category=None), config, storage)
        handle_clean(argparse.Namespace(policy="upsert", all=False), config, storage)
        handle_summarize(argparse.Namespace(id=None, all=True, unsummarized=True, limit=args.limit, force=False), config, storage)
        handle_analyze(argparse.Namespace(date_from=None, date_to=None, category=None, limit=50), config, storage)
        handle_report(argparse.Namespace(format="both", top_n=5), config, storage)
        handle_export(argparse.Namespace(format="all", status="summarized", category=None), config, storage)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()