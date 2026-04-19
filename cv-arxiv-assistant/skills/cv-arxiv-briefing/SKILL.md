---
name: cv-arxiv-briefing
description: Track the latest arXiv papers for computer vision, especially object detection, vision-language models, remote sensing, and UAV or drone imagery. Use when Codex needs to collect recent papers, prioritize what to read, group papers by CV subtopic, and write or refresh a Chinese markdown briefing with reviewer-style novelty scoring, author lists with first affiliations, clear research background and motivation, and concise innovation summaries.
---

# CV ArXiv Briefing

Produce a Chinese daily reading brief instead of a generic paper list.

## Workflow

1. Read `config/topics.json` to confirm the feeds and topic keywords.
2. Run `python scripts/daily_digest.py --output README.md` to generate the first-pass Chinese briefing.
3. Read the generated `README.md` and refine the top papers when the user asks for deeper judgment.
4. For each priority paper, always write these fields in Chinese:
   - `作者与第一单位`
   - `研究背景与动机`
   - `创新性评分`
   - `评分依据`
   - `关键创新点`
   - `每个创新点主要解决了什么问题`
5. Treat the score as a quick reviewer-style triage score from `1` to `5`:
   - `1/5`: mostly incremental, engineering cleanup, survey, or dataset-style contribution
   - `2/5`: limited method novelty, but still useful for practice or benchmarking
   - `3/5`: moderate novelty, clear method contribution, worth reading
   - `4/5`: strong idea or strong cross-domain combination, likely influential
   - `5/5`: unusually fresh direction, paradigm shift, or highly distinctive framing
6. Keep the score conservative when only the title and abstract are available. State uncertainty instead of overstating novelty.

## Output Standard

Keep the markdown focused on fast triage and write all narrative text in Chinese:

- start the README with a short daily summary block
- the summary block must explicitly state:
  - how many papers were scanned in total
  - how many topic-matched papers were published today
- `今日优先阅读` first
- topic buckets next
- concise Chinese summaries instead of long rewrites
- clear arXiv links for browsing
- explain the paper like a fast but careful reviewer, not like a translator
- list all authors and each author's first affiliation when available from arXiv metadata
- if affiliation metadata is missing, state that explicitly instead of guessing

## Tuning Guidance

- Favor papers that hit multiple topics such as detection plus remote sensing, or VLM plus grounding.
- For remote sensing and UAV imagery, pay attention to aerial, geospatial, SAR, hyperspectral, and low-altitude cues.
- If the user asks for a narrower focus, update `config/topics.json` rather than rewriting the script logic.
- When judging novelty, prioritize method-level contributions over pure scaling, dataset size, or training tricks.
- When writing `作者与第一单位`, list every author in order and give the first affiliation attached to that author.
- Do not invent affiliations. If arXiv metadata does not provide one, write `未提供单位信息`.
- When counting `今天命中了多少篇`, use the paper publish date converted to local time and count only topic-matched papers from that local calendar day.
- When writing `研究背景与动机`, answer:
  - what broader task or application setting the paper sits in
  - what limitation of prior work the authors are trying to fix
  - why the problem matters for deployment, scientific value, or benchmark progress
- When writing `关键创新点`, keep each point short and tie it to the bottleneck it addresses.
- If the abstract is vague, say that the score is preliminary and recommend opening the full PDF.

## Files

- `scripts/daily_digest.py`: collects RSS items, enriches author metadata, scores papers, and writes markdown
- `config/topics.json`: feed list and topic keywords
- `README.md`: daily output target
