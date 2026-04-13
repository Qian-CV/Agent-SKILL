#!/usr/bin/env python3
"""Generate a Chinese topic-focused arXiv daily markdown briefing."""

from __future__ import annotations

import argparse
import json
import re
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "topics.json"
RSS_URL = "https://rss.arxiv.org/rss/{feed}"
MAX_SNIPPET = 280
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Paper:
    arxiv_id: str
    title: str
    summary: str
    link: str
    authors: str
    feed: str
    published: datetime
    matched_topics: list[str]
    matched_keywords: list[str]
    score: int
    novelty_score: int
    novelty_rationale: str


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_feed(feed: str) -> bytes:
    request = urllib.request.Request(
        RSS_URL.format(feed=feed),
        headers={"User-Agent": "cv-arxiv-daily-brief/0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_id(link: str) -> str:
    tail = link.rstrip("/").split("/")[-1]
    return tail or link


def split_sentences(text: str) -> list[str]:
    sentences = [normalize_spaces(part) for part in SENTENCE_SPLIT_RE.split(text) if normalize_spaces(part)]
    return sentences


def pick_background(summary: str, matched_topics: list[str]) -> str:
    topic_map = {
        "object-detection": "目标检测",
        "vlm": "视觉语言建模",
        "remote-sensing": "遥感影像理解",
        "uav-drone": "无人机低空影像分析",
    }
    sentences = split_sentences(summary)
    if sentences:
        lead = truncate(sentences[0], 120)
    else:
        lead = "摘要中没有足够的上下文。"
    topics = [topic_map.get(topic, topic) for topic in matched_topics]
    if topics:
        return f"论文聚焦于{ '、'.join(topics) }相关问题。根据摘要，核心背景可概括为：{lead}"
    return f"从摘要看，这项工作面向一个通用视觉任务。核心背景可概括为：{lead}"


def pick_motivation(summary: str) -> str:
    lowered = summary.lower()
    motivation_patterns = [
        ("challenging", "作者强调该任务仍然具有较强挑战性，现有方法在复杂场景下可能不稳定。"),
        ("limited", "作者指出现有方法存在明显局限，说明当前方案在泛化、效率或鲁棒性上仍有缺口。"),
        ("robust", "动机之一可能是提升模型在真实场景中的鲁棒性与稳定性。"),
        ("efficient", "动机之一可能是降低计算或部署成本，提高训练和推理效率。"),
        ("generaliz", "作者可能希望提升跨场景、跨域或跨任务的泛化能力。"),
        ("small object", "摘要暗示小目标或细粒度目标仍然难以可靠识别，这通常是该工作的直接动机。"),
        ("ground", "摘要表明跨模态对齐或 grounding 能力仍不足，这通常是推动方法设计的关键动机。"),
    ]
    for pattern, text in motivation_patterns:
        if pattern in lowered:
            return text
    sentences = split_sentences(summary)
    if len(sentences) > 1:
        return f"从摘要描述看，作者的主要动机是解决这样一个瓶颈：{truncate(sentences[1], 140)}"
    return "摘要没有直接展开动机，我倾向于认为作者是在尝试弥补现有方案在效果、泛化或效率上的短板。"


def extract_innovations(summary: str) -> list[str]:
    cues = (
        "we propose",
        "we present",
        "we introduce",
        "this paper proposes",
        "this work proposes",
        "our method",
        "our framework",
        "we develop",
        "we design",
    )
    sentences = split_sentences(summary)
    picked: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(cue in lowered for cue in cues):
            picked.append(sentence)
    if not picked and sentences:
        picked = sentences[:2]
    return [truncate(sentence, 160) for sentence in picked[:3]]


def innovation_problem_map(innovation: str) -> str:
    lowered = innovation.lower()
    if any(token in lowered for token in ("efficient", "lightweight", "fast", "speed")):
        return "主要试图缓解计算开销大、部署效率低的问题。"
    if any(token in lowered for token in ("robust", "noise", "occlusion", "domain", "generaliz")):
        return "主要试图缓解复杂场景下鲁棒性不足和跨域泛化差的问题。"
    if any(token in lowered for token in ("ground", "language", "multimodal", "vision-language", "vlm")):
        return "主要试图缓解视觉与语言对齐不充分、语义 grounding 不稳定的问题。"
    if any(token in lowered for token in ("small object", "oriented", "remote", "aerial", "drone", "sar")):
        return "主要试图缓解遥感或低空场景中小目标、密集目标或特殊视角建模困难的问题。"
    return "主要试图缓解现有方法在表示能力、训练稳定性或任务适配性上的不足。"


def score_novelty(title: str, summary: str, matched_topics: list[str]) -> tuple[int, str]:
    text = f"{title} {summary}".lower()
    score = 2
    reasons: list[str] = []

    strong_positive = {
        "first": 1,
        "new paradigm": 2,
        "unified": 1,
        "generalist": 1,
        "foundation": 1,
        "scaling": 1,
        "open-vocabulary": 1,
        "world model": 2,
        "agent": 1,
    }
    mild_positive = {
        "novel": 1,
        "benchmark": 1,
        "dataset": 0,
        "comprehensive": 0,
        "large-scale": 1,
        "end-to-end": 1,
    }
    negative = {
        "survey": -1,
        "review": -1,
        "empirical study": -1,
        "analysis": -1,
        "dataset": -1,
    }

    for token, delta in strong_positive.items():
        if token in text:
            score += delta
            reasons.append(f"出现“{token}”这类较强创新信号")
    for token, delta in mild_positive.items():
        if token in text:
            score += delta
            if delta > 0:
                reasons.append(f"包含“{token}”这类方法层面的积极信号")
    for token, delta in negative.items():
        if token in text:
            score += delta
            reasons.append(f"更像“{token}”型工作，方法创新性可能略弱")

    if len(matched_topics) >= 2:
        score += 1
        reasons.append("同时命中多个关注方向，交叉问题价值更高")

    score = max(1, min(5, score))
    if not reasons:
        reasons.append("摘要提供的信息有限，当前评分更偏保守")
    rationale = "；".join(reasons[:3]) + "。"
    return score, rationale


def score_paper(title: str, summary: str, topics: dict[str, list[str]]) -> tuple[list[str], list[str], int]:
    haystack = f"{title} {summary}".lower()
    matched_topics: list[str] = []
    matched_keywords: list[str] = []
    score = 0

    for topic, keywords in topics.items():
        topic_hit = False
        for keyword in keywords:
            if keyword.lower() in haystack:
                matched_keywords.append(keyword)
                score += 3 if keyword.lower() in title.lower() else 1
                topic_hit = True
        if topic_hit:
            matched_topics.append(topic)

    return matched_topics, sorted(set(matched_keywords)), score


def parse_feed(feed: str, payload: bytes, topics: dict[str, list[str]]) -> list[Paper]:
    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is None:
        return []

    creator_tag = "{http://purl.org/dc/elements/1.1/}creator"
    papers: list[Paper] = []

    for item in channel.findall("item"):
        title = strip_html(item.findtext("title", default="Untitled"))
        summary = strip_html(item.findtext("description", default=""))
        link = item.findtext("link", default="").strip()
        authors = strip_html(item.findtext(creator_tag, default="Unknown authors"))
        published = parse_date(item.findtext("pubDate", default=""))
        arxiv_id = extract_id(link)
        matched_topics, matched_keywords, score = score_paper(title, summary, topics)
        novelty_score, novelty_rationale = score_novelty(title, summary, matched_topics)
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=title,
                summary=summary,
                link=link,
                authors=authors,
                feed=feed,
                published=published,
                matched_topics=matched_topics,
                matched_keywords=matched_keywords,
                score=score,
                novelty_score=novelty_score,
                novelty_rationale=novelty_rationale,
            )
        )

    return papers


def dedupe(papers: Iterable[Paper]) -> list[Paper]:
    best_by_id: dict[str, Paper] = {}
    for paper in papers:
        current = best_by_id.get(paper.arxiv_id)
        if current is None or (paper.score, paper.published) > (current.score, current.published):
            best_by_id[paper.arxiv_id] = paper
    return list(best_by_id.values())


def truncate(text: str, limit: int = MAX_SNIPPET) -> str:
    if len(text) <= limit:
        return text
    return textwrap.shorten(text, width=limit, placeholder="...")


def format_paper(paper: Paper) -> str:
    keywords = "、".join(paper.matched_keywords[:6]) if paper.matched_keywords else "通用 CV 相关"
    topics = "、".join(paper.matched_topics) if paper.matched_topics else "general-watchlist"
    published = paper.published.strftime("%Y-%m-%d %H:%M UTC")
    background = pick_background(paper.summary, paper.matched_topics)
    motivation = pick_motivation(paper.summary)
    innovations = extract_innovations(paper.summary)
    innovation_lines = []
    for index, innovation in enumerate(innovations, start=1):
        innovation_lines.append(
            f"  {index}. 创新点：{innovation}\n"
            f"     解决问题：{innovation_problem_map(innovation)}"
        )
    if not innovation_lines:
        innovation_lines.append("  1. 创新点：摘要没有明确写出方法设计，建议打开原文进一步确认。")
    return (
        f"### {paper.title}\n"
        f"- arXiv: [{paper.arxiv_id}]({paper.link})\n"
        f"- 作者: {paper.authors}\n"
        f"- 来源分区: `{paper.feed}`\n"
        f"- 发布时间: {published}\n"
        f"- 关注主题: {topics}\n"
        f"- 命中关键词: {keywords}\n"
        f"- 创新性评分: {paper.novelty_score}/5\n"
        f"- 评分依据: {paper.novelty_rationale}\n"
        f"- 研究背景与动机: {background} {motivation}\n"
        f"- 方法摘要: {truncate(paper.summary)}\n"
        f"- 关键创新点:\n" + "\n".join(innovation_lines) + "\n"
    )


def build_markdown(papers: list[Paper], max_papers: int, max_per_topic: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    matched = [paper for paper in papers if paper.score > 0]
    matched.sort(key=lambda paper: (paper.score, paper.novelty_score, paper.published), reverse=True)
    priority = matched[:max_papers]

    topic_sections: dict[str, list[Paper]] = {}
    for paper in matched:
        for topic in paper.matched_topics:
            topic_sections.setdefault(topic, [])
            if len(topic_sections[topic]) < max_per_topic:
                topic_sections[topic].append(paper)

    lines = [
        "# CV arXiv 中文简报",
        "",
        f"- 生成时间: {now}",
        f"- 扫描候选论文数: {len(papers)}",
        f"- 命中主题论文数: {len(matched)}",
        "- 说明: 创新性评分是基于标题与摘要的启发式初评，用于快速筛读，不等同于正式审稿结论。",
        "",
        "## 今日优先阅读",
        "",
    ]

    if priority:
        for paper in priority:
            lines.append(format_paper(paper))
    else:
        lines.extend(
            [
                "No topic-matched papers were found in the selected feeds.",
                "今天在选定 feed 中没有匹配到关注主题的论文。",
                "",
            ]
        )

    for topic in sorted(topic_sections):
        lines.extend([f"## 主题: {topic}", ""])
        for paper in topic_sections[topic]:
            lines.append(format_paper(paper))

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=ROOT / "README.md")
    parser.add_argument("--max-papers", type=int, default=10)
    parser.add_argument("--max-per-topic", type=int, default=5)
    args = parser.parse_args()

    config = load_config(args.config)
    feeds = config.get("feeds", [])
    topics = config.get("topics", {})

    collected: list[Paper] = []
    for feed in feeds:
        payload = fetch_feed(feed)
        collected.extend(parse_feed(feed, payload, topics))

    papers = dedupe(collected)
    markdown = build_markdown(papers, max_papers=args.max_papers, max_per_topic=args.max_per_topic)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"Wrote digest to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
