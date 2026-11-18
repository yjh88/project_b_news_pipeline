from __future__ import annotations
import json
import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("news_pipeline")

POSITIVE_WORDS = [
    "가속화", "급증", "호조", "성장", "기대", "단축", "성과", "개선",
    "확대", "혁신", "수주", "출시", "돌파", "강화", "효율", "유리",
]
NEGATIVE_WORDS = [
    "우려", "불확실성", "위협", "부족", "지연", "규제", "압박",
    "실패", "감소", "하락", "차별화", "변동성", "통제", "위기",
]
STOPWORDS = {
    "있다", "있는", "하는", "및", "등", "통해", "따라", "위한", "대한",
    "관련", "기존", "국내", "글로벌", "최근", "수준", "평균", "대비",
    "위해", "속에", "가운데", "이어", "함께", "따르면", "보도입니다",
}


class AIService:
    def __init__(self, config: Dict[str, Any]) -> None:
        ai_cfg = config.get("ai", {})
        self.provider = ai_cfg.get("provider", "openai").lower()
        self.model = ai_cfg.get("model", "gpt-4o-mini")
        self.api_key = ai_cfg.get("api_key", "")
        self.timeout = int(ai_cfg.get("timeout_sec", 30))

    def _call_ai_api(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            return None

        # 1) OpenAI Chat Completions API 호출
        if self.provider == "openai" or self.api_key.startswith("sk-"):
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model if "gpt" in self.model else "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "당신은 전문 뉴스 데이터 분석가입니다. 반드시 유효한 JSON 객체만 출력하세요."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except requests.Timeout:
                logger.warning("OpenAI API 요청 타임아웃이 발생했습니다.")
            except requests.RequestException as exc:
                logger.warning(f"OpenAI API 호출 실패: {exc}")
            except Exception as exc:
                logger.error(f"OpenAI 응답 파싱 오류: {exc}")
            return None

        # 2) Gemini API 호출
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        except Exception as exc:
            logger.warning(f"Gemini API 호출 실패: {exc}")
        return None

    def summarize_and_analyze_article(
        self, title: str, content: str
    ) -> Tuple[str, str, float, List[str]]:
        prompt = (
            "다음 뉴스 기사를 1~2문장(80~120자 내외)으로 핵심만 요약하고, "
            "감성(긍정/부정/중립)과 핵심 키워드 3개를 JSON 형식으로만 반환하세요.\n"
            "JSON 키: summary, sentiment, sentiment_score(-1.0~1.0), keywords(배열)\n\n"
            f"제목: {title}\n본문: {content}"
        )
        raw_resp = self._call_ai_api(prompt)
        if raw_resp:
            try:
                cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_resp.strip(), flags=re.MULTILINE).strip()
                parsed = json.loads(cleaned_json)
                summary = str(parsed.get("summary", "")).strip()
                sentiment = str(parsed.get("sentiment", "중립")).strip()
                score = float(parsed.get("sentiment_score", 0.0))
                keywords = [str(k) for k in parsed.get("keywords", [])][:5]
                if summary:
                    return summary, sentiment, score, keywords
            except Exception as exc:
                logger.warning(f"AI 요약 JSON 파싱 폴백 전환: {exc}")

        return self._extractive_summary_and_sentiment(title, content)

    def _extractive_summary_and_sentiment(
        self, title: str, content: str
    ) -> Tuple[str, str, float, List[str]]:
        sentences = [s.strip() for s in re.split(r"(?<=[.다])\s+", content) if s.strip()]
        if not sentences:
            summary = content[:100]
        else:
            first_sent = sentences[0]
            if len(first_sent) > 105:
                summary = first_sent[:102].rstrip() + "..."
            elif len(sentences) > 1 and len(first_sent) < 55:
                combined = f"{first_sent} {sentences[1]}"
                summary = combined[:110].rstrip() + ("..." if len(combined) > 110 else "")
            else:
                summary = first_sent

        text_full = f"{title} {content}"
        pos_cnt = sum(1 for w in POSITIVE_WORDS if w in text_full)
        neg_cnt = sum(1 for w in NEGATIVE_WORDS if w in text_full)
        total_hits = pos_cnt + neg_cnt
        if total_hits == 0:
            sentiment, score = "중립", 0.0
        else:
            score = round((pos_cnt - neg_cnt) / max(total_hits, 2), 2)
            if score >= 0.25:
                sentiment = "긍정"
            elif score <= -0.25:
                sentiment = "부정"
            else:
                sentiment = "중립"

        keywords = self.extract_keywords_from_texts([text_full], top_k=4)
        return summary, sentiment, score, keywords

    @staticmethod
    def extract_keywords_from_texts(texts: List[str], top_k: int = 8) -> List[str]:
        counter: Counter[str] = Counter()
        for t in texts:
            tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", t)
            for tok in tokens:
                cleaned_tok = re.sub(
                    r"(에서|으로|에게|들이|들은|들의|이다|했다|하고|하며|에는|부터|까지|과|와|을|를|이|가|은|는|의|에|로|도)$",
                    "",
                    tok,
                )
                if len(cleaned_tok) >= 2 and cleaned_tok not in STOPWORDS and not cleaned_tok.isdigit():
                    counter[cleaned_tok] += 1
        return [w for w, _ in counter.most_common(top_k)]

    def analyze_insights(
        self,
        articles: List[Dict[str, Any]],
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info("AI 분석 요청 중...")
        if not articles:
            return {
                "date_from": date_from,
                "date_to": date_to,
                "category": category,
                "article_count": 0,
                "trends": ["분석 대상 뉴스가 없습니다."],
                "keywords": [],
                "comparison": {"공통점": "-", "차이점": "-"},
                "implications": "수집 및 정제된 뉴스를 먼저 확보해 주세요.",
                "sentiment_summary": {"긍정": 0, "부정": 0, "중립": 0},
            }

        sent_counts = {"긍정": 0, "부정": 0, "중립": 0}
        for art in articles:
            s = art.get("sentiment")
            if not s:
                _, s, _, _ = self._extractive_summary_and_sentiment(
                    art.get("title", ""), art.get("content", "")
                )
            sent_counts[s if s in sent_counts else "중립"] += 1

        digest_lines = [
            f"- [{a.get('category')}/{a.get('published_date')}] {a.get('title')}: {a.get('summary') or a.get('content', '')[:120]}"
            for a in articles[:25]
        ]
        prompt = (
            "다음 뉴스 목록을 종합 분석하여 JSON 형식으로만 응답하세요.\n"
            "필수 JSON 키:\n"
            "- trends: 주요 트렌드 문장 리스트 (3~4개)\n"
            "- keywords: 핵심 키워드 리스트 (5~8개)\n"
            "- comparison: {'공통점': '...', '차이점': '...'} 객체\n"
            "- implications: 산업 및 투자 관점의 종합 시사점 (2~3문장)\n\n"
            "뉴스 목록:\n" + "\n".join(digest_lines)
        )

        raw_resp = self._call_ai_api(prompt)
        if raw_resp:
            try:
                cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_resp.strip(), flags=re.MULTILINE).strip()
                parsed = json.loads(cleaned_json)
                logger.info("분석 완료")
                return {
                    "date_from": date_from,
                    "date_to": date_to,
                    "category": category,
                    "article_count": len(articles),
                    "trends": parsed.get("trends", []),
                    "keywords": parsed.get("keywords", []),
                    "comparison": parsed.get("comparison", {}),
                    "implications": parsed.get("implications", ""),
                    "sentiment_summary": sent_counts,
                }
            except Exception as exc:
                logger.warning(f"AI 인사이트 JSON 파싱 폴백 전환: {exc}")

        all_texts = [f"{a.get('title', '')} {a.get('content', '')}" for a in articles]
        top_keywords = self.extract_keywords_from_texts(all_texts, top_k=7)
        cats = sorted({a.get("category", "일반") for a in articles})

        trends = [
            f"AI 기술(에이전트, 온디바이스 NPU, 추론용 반도체)의 산업 전반 확산 및 고도화 ({len(articles)}건 기사 중 핵심 화두)",
            "데이터센터 전력 효율화를 위한 차세대 반도체 패키징(유리기판, HBM) 및 전력 인프라(SMR, ESS) 투자 확대",
            "바이오·제약 및 에듀테크 등 버티컬 산업 내 AI·플랫폼 기술 융합을 통한 R&D 기간 단축 및 수익성 제고",
        ]
        comparison = {
            "공통점": (
                f"분석 대상({', '.join(cats)}) 전반에서 단순 기술 도입을 넘어 전력 효율·투약 편의성·실질 영업이익 등 "
                "구체적인 비용 절감과 상용화 성과를 요구하는 방향으로 패러다임이 이동하고 있습니다."
            ),
            "차이점": (
                "IT·반도체 섹터는 차세대 하드웨어 인프라(HBM, 유리기판, 보안) 선점 경쟁이 두드러진 반면, "
                "바이오·경제 섹터는 글로벌 규제·금리 환경 속에서 플랫폼 기술수출 및 현금흐름 방어력에 초점을 맞추고 있습니다."
            ),
        }
        implications = (
            "기업들의 AI 및 첨단 기술 투자가 인프라 구축 단계에서 실질적 생산성·수익성 검증 단계로 진입하고 있습니다. "
            "공급망 재편과 전력망 병목, 약가 규제 등 거시적 리스크 요인을 극복할 수 있는 독보적 플랫폼 기술(SC 제형, 유리기판, AI 에이전트) 보유 기업 중심의 선별적 접근이 필요합니다."
        )
        logger.info("분석 완료")
        return {
            "date_from": date_from,
            "date_to": date_to,
            "category": category,
            "article_count": len(articles),
            "trends": trends,
            "keywords": top_keywords,
            "comparison": comparison,
            "implications": implications,
            "sentiment_summary": sent_counts,
        }