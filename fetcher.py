from __future__ import annotations
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("news_pipeline")

# 네트워크 오류나 오프라인 테스트 시에도 파이프라인을 검증할 수 있는 현실적인 샘플 데이터
SAMPLE_RAW_NEWS: List[Dict[str, Any]] = [
    {
        "title": "글로벌 빅테크, 차세대 AI 에이전트 및 추론형 반도체 도입 가속화",
        "url": "https://news.example.com/it/1001",
        "content": (
            "글로벌 클라우드 및 빅테크 기업들이 생성형 AI를 넘어 자율적으로 업무를 수행하는 AI 에이전트(Agent) 서비스를 잇따라 출시하고 있다. "
            "이에 따라 데이터센터 내 추론(Inference) 연산 효율을 극대화하는 맞춤형 AI 반도체(ASIC)와 고대역폭메모리(HBM) 수요가 급증하고 있으며, "
            "국내 반도체 업계도 차세대 HBM4 양산 준비와 패키징 공정 고도화에 속도를 내고 있다."
        ),
        "published_at": "2026-11-12 09:30:00",
        "category": "IT",
        "source_name": "naver",
        "fetch_method": "crawl",
    },
    {
        "title": "클라우드 보안 및 제로트러스트 아키텍처, 금융권 도입 확산",
        "url": "https://news.example.com/it/1002",
        "content": (
            "금융권과 공공기관의 클라우드 전환이 가속화되면서 사이버 보안 위협에 대응하기 위한 제로트러스트(Zero Trust) 보안 모델 도입이 본격화되고 있다. "
            "AI 기반 이상 징후 탐지 시스템(SIEM)을 통해 실시간 해킹 시도를 차단하고 내부 데이터 유출을 방지하는 솔루션 투자가 전년 대비 35% 이상 증가했다."
        ),
        "published_at": "2026-11-13 14:15:00",
        "category": "IT",
        "source_name": "naver",
        "fetch_method": "crawl",
    },
    {
        "title": "바이오 의약품 피하주사(SC) 제형 변경 플랫폼, 글로벌 기술수출 호조",
        "url": "https://news.example.com/bio/2001",
        "content": (
            "기존 정맥주사(IV) 방식의 항암제 및 자가면역질환 치료제를 환자 투약 편의성이 높은 피하주사(SC) 제형으로 전환하는 바이오 플랫폼 기술이 글로벌 제약 시장에서 핵심 경쟁력으로 부상하고 있다. "
            "미국 약가 인하 압박 속에서도 특허 만료 방어와 투약 시간 단축 효과를 노린 글로벌 빅파마들의 기술 도입 계약이 잇따르고 있어 국내 바이오텍의 로열티 수익 성장이 기대된다."
        ),
        "published_at": "2026-11-14 10:20:00",
        "category": "바이오",
        "source_name": "yonhap_rss",
        "fetch_method": "rss",
    },
    {
        "title": "AI 신약개발 플랫폼, 후보물질 발굴 기간 절반 단축 성과",
        "url": "https://news.example.com/bio/2002",
        "content": (
            "단백질 구조 예측 AI와 생성형 화학 모델을 결합한 AI 신약개발 파이프라인이 전임상 후보물질 도출 기간을 기존 평균 4년에서 1년 반 수준으로 단축시키는 성과를 내고 있다. "
            "제약사들은 자체 AI 연구소를 설립하거나 AI 전문 바이오벤처와의 공동 연구 계약을 확대하며 임상 실패 확률을 낮추는 데 주력하고 있다."
        ),
        "published_at": "2026-11-14 16:40:00",
        "category": "바이오",
        "source_name": "yonhap_rss",
        "fetch_method": "rss",
    },
    {
        "title": "반도체 패키징 유리기판 상용화 경쟁 본격화…전력 효율 40% 개선",
        "url": "https://news.example.com/semi/3001",
        "content": (
            "초거대 AI 모델 구동에 따른 데이터센터 전력 소모 문제가 대두되면서, 기존 플라스틱 기판을 대체할 차세대 반도체 유리기판(Glass Substrate) 상용화 경쟁이 치열해지고 있다. "
            "유리기판은 표면이 매끄러워 미세 회로 구현에 유리하고 열 변형이 적어 전력 효율을 최대 40%까지 개선할 수 있어 소재·부품·장비 기업들의 신규 수주가 이어지고 있다."
        ),
        "published_at": "2026-11-15 11:05:00",
        "category": "반도체",
        "source_name": "naver",
        "fetch_method": "crawl",
    },
    {
        "title": "반도체 공급망 재편과 수출 규제 강화에 따른 설비투자 불확실성 지속",
        "url": "https://news.example.com/semi/3002",
        "content": (
            "글로벌 반도체 공급망 재편과 첨단 장비 수출 통제 조치가 강화되면서 일부 레거시 공정 라인의 가동률 조정과 설비투자(CAPEX) 속도 조절 우려가 제기되고 있다. "
            "전문가들은 범용 메모리 가격 변동성에 대비해 고부가가치 선단 공정 중심으로 포트폴리오를 재편해야 한다고 지적했다."
        ),
        "published_at": "2026-11-15 17:50:00",
        "category": "반도체",
        "source_name": "yonhap_rss",
        "fetch_method": "rss",
    },
    {
        "title": "온디바이스 AI 스마트폰 및 노트북 출시 확대…신경망처리장치(NPU) 성능 경쟁",
        "url": "https://news.example.com/it/1003",
        "content": (
            "클라우드 서버를 거치지 않고 기기 자체에서 실시간 통번역, 문서 요약, 이미지 편집을 처리하는 온디바이스(On-Device) AI 기기 출시가 본격화되었다. "
            "개인정보 보호와 응답 속도 개선이라는 장점을 앞세워 스마트폰과 초경량 노트북 제조사들이 고성능 NPU 탑재 비중을 빠르게 늘리고 있다."
        ),
        "published_at": "2026-11-16 08:45:00",
        "category": "IT",
        "source_name": "naver",
        "fetch_method": "crawl",
    },
    {
        "title": "고금리 장기화 우려 속 기술주 밸류에이션 차별화 심화",
        "url": "https://news.example.com/economy/4001",
        "content": (
            "글로벌 거시경제의 금리 인하 속도 조절론이 부각되면서 증시 내 기술주와 성장주 간 옥석 가리기가 심화되고 있다. "
            "단기적인 테마성 기대감보다는 실질적인 영업이익 성장과 기술 수출 계약, 확실한 현금흐름을 증명하는 기업 중심으로 기관 투자자의 수급이 집중되는 양상이다."
        ),
        "published_at": "2026-11-16 15:10:00",
        "category": "경제",
        "source_name": "google_rss",
        "fetch_method": "rss",
    },
    {
        "title": "국내 에듀테크 업계, 맞춤형 AI 튜터 및 자동 첨삭 솔루션 도입 확대",
        "url": "https://news.example.com/it/1004",
        "content": (
            "교육 현장에서 학습자의 수준을 진단하고 맞춤형 국어·영어 독해 지문 분석과 서술형 첨삭을 지원하는 AI 튜터 서비스 도입이 빠르게 늘고 있다. "
            "거대언어모델(LLM)에 정교한 교육과정 루브릭 프롬프트를 결합해 교사와 강사의 수업 준비 시간을 단축하고 학습 피드백의 정확도를 높이고 있다."
        ),
        "published_at": "2026-11-17 09:00:00",
        "category": "IT",
        "source_name": "google_rss",
        "fetch_method": "rss",
    },
    {
        "title": "차세대 데이터센터 전력망 부족 문제 심화…소형모듈원전(SMR) 및 ESS 주목",
        "url": "https://news.example.com/economy/4002",
        "content": (
            "AI 데이터센터 증설로 인해 글로벌 전력 소비량이 급증하면서 안정적인 무탄소 전력원 확보가 빅테크 기업의 핵심 과제로 떠올랐다. "
            "송배전망 확충 지연과 전력 부족 우려 속에 소형모듈원전(SMR) 장기 전력구매계약(PPA)과 대용량 에너지저장장치(ESS) 투자가 동반 확대되고 있다."
        ),
        "published_at": "2026-11-17 11:30:00",
        "category": "경제",
        "source_name": "yonhap_rss",
        "fetch_method": "rss",
    },
    # 3단계(정제) 테스트를 위한 중복 및 필수필드 누락 샘플
    {
        "title": "글로벌 빅테크, 차세대 AI 에이전트 및 추론형 반도체 도입 가속화",
        "url": "https://news.example.com/it/1001",
        "content": (
            "글로벌 클라우드 및 빅테크 기업들이 생성형 AI를 넘어 자율적으로 업무를 수행하는 AI 에이전트(Agent) 서비스를 잇따라 출시하고 있다. "
            "이에 따라 데이터센터 내 추론(Inference) 연산 효율을 극대화하는 맞춤형 AI 반도체(ASIC)와 고대역폭메모리(HBM) 수요가 급증하고 있으며, "
            "국내 반도체 업계도 차세대 HBM4 양산 준비와 패키징 공정 고도화에 속도를 내고 있다."
        ),
        "published_at": "2026.11.12",
        "category": "IT",
        "source_name": "naver",
        "fetch_method": "crawl",
    },
    {
        "title": "   ",
        "url": "https://news.example.com/invalid/9999",
        "content": "짧은 텍스트",
        "published_at": "",
        "category": None,
        "source_name": "naver",
        "fetch_method": "crawl",
    },
]


class NewsFetcher:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        crawler_cfg = config.get("crawler", {})
        self.timeout = int(crawler_cfg.get("timeout_sec", 10))
        self.delay = float(crawler_cfg.get("delay_sec", 1.0))
        self.headers = {
            "User-Agent": crawler_cfg.get("user_agent", "Mozilla/5.0 (compatible; NewsTrendBot/1.0)")
        }

    def fetch(
        self,
        source: str = "all",
        limit: int = 20,
        category_override: Optional[str] = None,
        use_sample_on_fail: bool = True,
    ) -> List[Dict[str, Any]]:
        logger.info(f"뉴스 수집 시작: source={source}, limit={limit}")
        collected: List[Dict[str, Any]] = []
        failed_count = 0

        if source.lower() in ("sample", "demo", "mock"):
            collected = self._fetch_sample(limit=limit, category_override=category_override)
            logger.info(f"수집 완료: {len(collected)}건 성공, 0건 실패")
            return collected

        sources_cfg = self.config.get("sources", {})
        target_sources = {source: sources_cfg[source]} if source in sources_cfg else sources_cfg

        for src_name, src_info in target_sources.items():
            if len(collected) >= limit:
                break
            src_type = src_info.get("type", "rss")
            url = src_info.get("url", "")
            cat = category_override or src_info.get("category", "IT")
            rem = limit - len(collected)

            if src_type == "rss":
                items, errs = self.fetch_from_rss(url, src_name, cat, limit=rem)
            else:
                items, errs = self.fetch_by_crawling(url, src_name, cat, limit=rem)

            collected.extend(items)
            failed_count += errs

        if not collected and use_sample_on_fail:
            logger.warning("외부 응답을 가져올 수 없어 내장 뉴스 데이터셋으로 대체 수집합니다.")
            collected = self._fetch_sample(limit=limit, category_override=category_override)

        logger.info(f"수집 완료: {len(collected)}건 성공, {failed_count}건 실패")
        return collected

    def fetch_from_rss(
        self, rss_url: str, source_name: str, category: str, limit: int = 10
    ) -> tuple[List[Dict[str, Any]], int]:
        results: List[Dict[str, Any]] = []
        errors = 0
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            resp = requests.get(rss_url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item_el in root.findall(".//item")[:limit]:
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                desc = (item_el.findtext("description") or "").strip()
                pub_date = (item_el.findtext("pubDate") or now_iso).strip()
                if "<" in desc and ">" in desc:
                    desc = BeautifulSoup(desc, "html.parser").get_text(" ", strip=True)
                if not desc or len(desc) < 20:
                    desc = f"{title} 관련 상세 뉴스 보도입니다."
                results.append(
                    {
                        "title": title,
                        "url": link,
                        "content": desc,
                        "published_at": pub_date,
                        "category": category,
                        "source_name": source_name,
                        "fetch_method": "rss",
                        "fetched_at": now_iso,
                    }
                )
        except requests.Timeout:
            logger.warning(f"RSS 타임아웃 발생 ({source_name}): {rss_url}")
            errors += 1
        except requests.RequestException as exc:
            logger.warning(f"RSS 요청 오류 ({source_name}): {exc}")
            errors += 1
        except ET.ParseError as exc:
            logger.error(f"RSS XML 파싱 오류 ({source_name}): {exc}")
            errors += 1
        return results, errors

    def fetch_by_crawling(
        self, page_url: str, source_name: str, category: str, limit: int = 10
    ) -> tuple[List[Dict[str, Any]], int]:
        results: List[Dict[str, Any]] = []
        errors = 0
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            resp = requests.get(page_url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for a_tag in soup.select("a[href]"):
                href = a_tag.get("href", "")
                text = a_tag.get_text(strip=True)
                if len(text) >= 12 and ("/article/" in href or "news" in href) and not href.startswith("javascript"):
                    full_url = urljoin(page_url, href)
                    if full_url not in [x[1] for x in links]:
                        links.append((text, full_url))
                if len(links) >= limit:
                    break

            for title, article_url in links[:limit]:
                time.sleep(min(self.delay, 1.5))
                content_text = title
                pub_date = now_iso
                try:
                    art_resp = requests.get(article_url, headers=self.headers, timeout=self.timeout)
                    art_resp.raise_for_status()
                    art_soup = BeautifulSoup(art_resp.text, "html.parser")
                    body_el = art_soup.select_one("#dic_area") or art_soup.select_one("article")
                    if body_el:
                        content_text = body_el.get_text(" ", strip=True)
                    time_el = art_soup.select_one("span.media_end_head_info_datestamp_time") or art_soup.select_one("time")
                    if time_el:
                        pub_date = time_el.get("data-date-time") or time_el.get_text(strip=True)
                except requests.RequestException as sub_exc:
                    logger.warning(f"개별 기사 크롤링 실패 ({article_url}): {sub_exc}")
                    errors += 1
                results.append(
                    {
                        "title": title,
                        "url": article_url,
                        "content": content_text,
                        "published_at": pub_date,
                        "category": category,
                        "source_name": source_name,
                        "fetch_method": "crawl",
                        "fetched_at": now_iso,
                    }
                )
        except requests.Timeout:
            logger.warning(f"크롤링 타임아웃 발생 ({source_name}): {page_url}")
            errors += 1
        except requests.RequestException as exc:
            logger.warning(f"크롤링 요청 실패 ({source_name}): {exc}")
            errors += 1
        return results, errors

    def _fetch_sample(
        self, limit: int = 20, category_override: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        items: List[Dict[str, Any]] = []
        for raw in SAMPLE_RAW_NEWS[:limit]:
            item = dict(raw)
            if category_override:
                item["category"] = category_override
            item["fetched_at"] = now_iso
            items.append(item)
        return items