# [Project B] AI 뉴스 트렌드 및 종합 분석 리포트 CLI 서비스

외부 뉴스 데이터(RSS/API 및 웹 크롤링)를 자동 수집하여 **Raw/Clean 저장소에 분리 저장**하고, **AI API(Gemini)를 활용한 본문 요약·감성 분석·인사이트 도출**부터 **시각화 차트(PNG) 및 종합 리포트(MD/TXT/CSV/Excel) 생성**까지 수행하는 End-to-End 데이터 파이프라인 CLI 애플리케이션입니다.

## 1. 프로젝트 구조 및 모듈 설계 (7개 핵심 모듈 분리)

단일 파일이 아닌 역할별로 명확히 분리된 모듈 아키텍처로 구성되어 있습니다.

```text
project_b_news_pipeline/
├── main.py              # argparse 기반 서브커맨드 CLI 엔트리포인트 (필수 6종 + 보너스 3종)
├── config_loader.py     # config.json, .env 환경변수 로드 및 logging(INFO/WARNING/ERROR) 초기화
├── storage.py           # 영구 저장소 모듈 (SQLite DB + raw/clean JSONL 파일 동기화 관리)
├── fetcher.py           # 뉴스 수집 모듈 (RSS/XML 파싱 + BeautifulSoup 크롤링 + 타임아웃/딜레이 제어)
├── cleaner.py           # 데이터 정제 모듈 (필수 필드 검증, 텍스트·날짜 정규화, skip/upsert 중복 처리)
├── ai_service.py        # AI 요약, 감성 분석(긍정/부정/중립) 및 트렌드·키워드·시사점 종합 분석 모듈
├── visualizer.py        # matplotlib 한글 폰트 설정 및 차트 4종(카테고리, 일자별 추이, 감성 분포, 대시보드) 생성
├── reporter.py          # 데이터 품질 지표·TOP N 집계·AI 인사이트 리포트(MD/TXT) 및 CSV/JSONL/Excel 내보내기
├── config.json          # 뉴스 소스 URL, 중복 정책, 저장 경로, 크롤링 타임아웃/딜레이 설정 파일
└── requirements.txt     # 필수 라이브러리 목록