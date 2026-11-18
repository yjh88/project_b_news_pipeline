from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

logger = logging.getLogger("news_pipeline")


def configure_korean_font() -> str:
    preferred_fonts = [
        "Malgun Gothic",
        "NanumGothic",
        "Noto Sans CJK KR",
        "Noto Sans KR",
        "AppleGothic",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font_name in preferred_fonts:
        if font_name in available:
            plt.rcParams["font.family"] = font_name
            plt.rcParams["axes.unicode_minus"] = False
            return font_name

    plt.rcParams["axes.unicode_minus"] = False
    return "sans-serif"


class NewsVisualizer:
    def __init__(self, output_dir: str = "output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.font_used = configure_korean_font()

    def generate_all_charts(self, metrics: Dict[str, Any]) -> Dict[str, str]:
        paths: Dict[str, str] = {}
        paths["category_chart"] = self.plot_category_distribution(metrics.get("by_category", []))
        paths["daily_trend_chart"] = self.plot_daily_trend(metrics.get("by_date", []))
        paths["sentiment_chart"] = self.plot_sentiment_distribution(metrics.get("by_sentiment", []))
        paths["overview_dashboard"] = self.plot_overview_dashboard(metrics)
        return paths

    def plot_category_distribution(self, by_category: List[Dict[str, Any]]) -> str:
        out_path = self.output_dir / "chart_category_dist.png"
        categories = [r["category"] for r in by_category] or ["데이터 없음"]
        counts = [r["cnt"] for r in by_category] or [0]

        fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
        colors = ["#2563EB", "#0D9488", "#7C3AED", "#D97706", "#DC2626"]
        bars = ax.bar(
            categories,
            counts,
            color=[colors[i % len(colors)] for i in range(len(categories))],
            width=0.55,
            edgecolor="#1E293B",
            linewidth=0.6,
        )
        ax.set_title("카테고리별 뉴스 수집 분포", fontsize=14, fontweight="bold", pad=14)
        ax.set_xlabel("카테고리", fontsize=11)
        ax.set_ylabel("뉴스 건수 (건)", fontsize=11)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_ylim(0, max(counts) * 1.25 + 1)

        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{int(height)}건",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )

        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        logger.info(f"카테고리별 분포 차트 저장 완료: {out_path}")
        return str(out_path)

    def plot_daily_trend(self, by_date: List[Dict[str, Any]]) -> str:
        out_path = self.output_dir / "chart_daily_trend.png"
        dates = [r["published_date"] for r in by_date] or ["N/A"]
        counts = [r["cnt"] for r in by_date] or [0]

        fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=150)
        ax.plot(
            dates,
            counts,
            marker="o",
            color="#0F766E",
            linewidth=2.4,
            markersize=7,
            markerfacecolor="#14B8A6",
        )
        ax.fill_between(range(len(dates)), counts, color="#14B8A6", alpha=0.15)
        ax.set_title("일자별 뉴스 발행·수집 추이", fontsize=14, fontweight="bold", pad=14)
        ax.set_xlabel("발행 일자", fontsize=11)
        ax.set_ylabel("뉴스 건수 (건)", fontsize=11)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.set_ylim(0, max(counts) * 1.3 + 1)
        plt.xticks(rotation=20)

        for i, v in enumerate(counts):
            ax.annotate(
                f"{v}건",
                xy=(i, v),
                xytext=(0, 7),
                textcoords="offset points",
                ha="center",
                fontsize=9.5,
                fontweight="bold",
            )

        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        logger.info(f"일자별 수집 추이 차트 저장 완료: {out_path}")
        return str(out_path)

    def plot_sentiment_distribution(self, by_sentiment: List[Dict[str, Any]]) -> str:
        out_path = self.output_dir / "chart_sentiment_dist.png"
        labels = [r["sentiment"] for r in by_sentiment] or ["중립"]
        counts = [r["cnt"] for r in by_sentiment] or [1]
        color_map = {"긍정": "#10B981", "중립": "#64748B", "부정": "#EF4444", "미분석": "#CBD5E1"}
        pie_colors = [color_map.get(lbl, "#3B82F6") for lbl in labels]

        fig, ax = plt.subplots(figsize=(6.8, 4.8), dpi=150)
        wedges, texts, autotexts = ax.pie(
            counts,
            labels=labels,
            autopct="%1.1f%%",
            startangle=140,
            colors=pie_colors,
            wedgeprops={"edgecolor": "white", "linewidth": 1.5},
            textprops={"fontsize": 11},
        )
        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontweight("bold")

        ax.set_title("AI 기반 뉴스 감성(긍정/부정/중립) 분포", fontsize=14, fontweight="bold", pad=12)
        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        logger.info(f"감성 분석 차트 저장 완료: {out_path}")
        return str(out_path)

    def plot_overview_dashboard(self, metrics: Dict[str, Any]) -> str:
        out_path = self.output_dir / "news_analysis_dashboard.png"
        by_cat = metrics.get("by_category", [])
        by_date = metrics.get("by_date", [])
        by_sent = metrics.get("by_sentiment", [])

        fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), dpi=150)
        fig.suptitle("AI 뉴스 트렌드 및 감성 분석 종합 시각화 리포트", fontsize=15, fontweight="bold", y=1.02)

        cats = [r["category"] for r in by_cat] or ["없음"]
        cat_cnts = [r["cnt"] for r in by_cat] or [0]
        bars = axes[0].bar(cats, cat_cnts, color=["#2563EB", "#0D9488", "#7C3AED", "#D97706"][: len(cats)], width=0.55)
        axes[0].set_title("1. 카테고리별 뉴스 수", fontsize=12, fontweight="bold")
        axes[0].set_ylabel("건수")
        axes[0].grid(axis="y", linestyle="--", alpha=0.4)
        axes[0].set_ylim(0, max(cat_cnts) * 1.25 + 1)
        for b in bars:
            axes[0].annotate(
                f"{int(b.get_height())}건",
                (b.get_x() + b.get_width() / 2, b.get_height()),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                fontsize=9.5,
                fontweight="bold",
            )

        dates = [r["published_date"][5:] for r in by_date] or ["N/A"]
        date_cnts = [r["cnt"] for r in by_date] or [0]
        axes[1].plot(dates, date_cnts, marker="o", color="#0F766E", linewidth=2.2)
        axes[1].fill_between(range(len(dates)), date_cnts, color="#14B8A6", alpha=0.15)
        axes[1].set_title("2. 일자별 수집 추이", fontsize=12, fontweight="bold")
        axes[1].set_ylabel("건수")
        axes[1].grid(True, linestyle="--", alpha=0.4)
        axes[1].set_ylim(0, max(date_cnts) * 1.3 + 1)
        for i, v in enumerate(date_cnts):
            axes[1].annotate(f"{v}건", (i, v), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=9)

        s_labels = [r["sentiment"] for r in by_sent] or ["중립"]
        s_cnts = [r["cnt"] for r in by_sent] or [1]
        color_map = {"긍정": "#10B981", "중립": "#64748B", "부정": "#EF4444", "미분석": "#CBD5E1"}
        axes[2].pie(
            s_cnts,
            labels=[f"{l} ({c}건)" for l, c in zip(s_labels, s_cnts)],
            autopct="%1.1f%%",
            startangle=135,
            colors=[color_map.get(l, "#3B82F6") for l in s_labels],
            wedgeprops={"edgecolor": "white", "linewidth": 1.2},
        )
        axes[2].set_title("3. 뉴스 감성 분석 분포", fontsize=12, fontweight="bold")

        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"종합 대시보드 차트 저장 완료: {out_path}")
        return str(out_path)