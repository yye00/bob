"""R7: arXiv literature scan agent.

Pulls daily abstracts from arXiv categories cs.MS, physics.comp-ph,
astro-ph.IM, nucl-th, and physics.plasm-ph. Filters for papers proposing
new methods, benchmarks, or open implementations. Emits Proposal objects
suggesting either new framework features or new application specs.
"""

from __future__ import annotations

import datetime
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from bob.research.proposal import Proposal

ARXIV_CATEGORIES: list[str] = [
    "cs.MS",
    "physics.comp-ph",
    "astro-ph.IM",
    "nucl-th",
    "physics.plasm-ph",
]

FILTER_KEYWORDS: list[str] = [
    "new method",
    "novel method",
    "propose",
    "benchmark",
    "open-source",
    "open source",
    "implementation",
    "code release",
    "software",
    "algorithm",
    "framework",
    "solver",
    "library",
    "toolkit",
]

_REJECT_KEYWORDS: list[str] = [
    "review",
    "survey",
    "overview",
    "tutorial",
    "introduction to",
]

_ARXIV_API = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}
_MAX_RESULTS_PER_CATEGORY = 10


def _paper_matches_filter(text: str) -> bool:
    """Return True if the abstract proposes a new method, benchmark, or open implementation."""
    lower = text.lower()
    # Must match at least one positive keyword
    has_positive = any(kw in lower for kw in FILTER_KEYWORDS)
    if not has_positive:
        return False
    # Must not be a pure review/survey (no other positive signal)
    has_reject = any(kw in lower for kw in _REJECT_KEYWORDS)
    if has_reject:
        # Accept only if it also has a strong positive signal beyond just "survey"
        strong_positive = [
            "propose", "new method", "novel method", "implementation",
            "open-source", "open source", "code release", "benchmark",
        ]
        return any(kw in lower for kw in strong_positive)
    return True


def _paper_to_proposal(paper: dict[str, Any]) -> Proposal:
    """Convert a paper dict to a Proposal."""
    arxiv_id = paper.get("id", "unknown")
    title = paper.get("title", "Untitled").strip()
    abstract = paper.get("abstract", "").strip()
    categories = paper.get("categories", [])
    authors = paper.get("authors", [])

    # Determine suggestion type based on abstract content
    lower = abstract.lower()
    if any(kw in lower for kw in ("benchmark", "test suite", "evaluation")):
        suggestion_type = "benchmark"
        ac_template = f"Integrate or evaluate '{title}' benchmark in the test suite"
    elif any(kw in lower for kw in ("open-source", "open source", "code release", "github")):
        suggestion_type = "open_implementation"
        ac_template = f"Evaluate open implementation from '{title}' for integration"
    else:
        suggestion_type = "new_method"
        ac_template = f"Prototype application spec based on method in '{title}'"

    categories_str = ", ".join(categories) if categories else "unknown"
    authors_str = ", ".join(authors[:3])
    if len(authors) > 3:
        authors_str += " et al."

    return Proposal(
        domain="literature",
        title=f"[arXiv {suggestion_type}] {title[:80]}",
        rationale=(
            f"arXiv paper in {categories_str} proposes a {suggestion_type.replace('_', ' ')} "
            f"relevant to scientific computing. "
            f"Authors: {authors_str}. "
            f"Abstract excerpt: {abstract[:200]}..."
        ),
        acceptance_criteria=[ac_template],
        estimated_effort="small",
        estimated_impact="medium",
        evidence=[
            f"arXiv:{arxiv_id}",
            f"categories:{categories_str}",
            f"scanned_by:r7_literature",
        ],
    )


def _fetch_arxiv_papers(
    category: str,
    max_results: int = _MAX_RESULTS_PER_CATEGORY,
) -> list[dict[str, Any]]:
    """Fetch recent papers from arXiv for a given category via the Atom API."""
    params = urllib.parse.urlencode({
        "search_query": f"cat:{category}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"{_ARXIV_API}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml_data = resp.read()
    except (urllib.error.URLError, OSError):
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", _NS):
        id_el = entry.find("atom:id", _NS)
        title_el = entry.find("atom:title", _NS)
        summary_el = entry.find("atom:summary", _NS)

        if id_el is None or title_el is None or summary_el is None:
            continue

        raw_id = id_el.text or ""
        # Strip URL prefix to get bare arXiv ID
        arxiv_id = raw_id.split("/abs/")[-1].strip()

        author_els = entry.findall("atom:author/atom:name", _NS)
        authors = [a.text.strip() for a in author_els if a.text]

        category_els = entry.findall("atom:category", _NS)
        categories = [
            c.get("term", "") for c in category_els if c.get("term")
        ]

        papers.append({
            "id": arxiv_id,
            "title": (title_el.text or "").strip().replace("\n", " "),
            "abstract": (summary_el.text or "").strip().replace("\n", " "),
            "categories": categories,
            "authors": authors,
        })

    return papers


def _generate_offline_proposals(round_num: int) -> list[Proposal]:
    """Generate baseline proposals when network is unavailable."""
    today = datetime.date.today().isoformat()
    return [
        Proposal(
            domain="literature",
            title="[arXiv scan] Schedule daily literature scan for scientific computing",
            rationale=(
                f"R7 arXiv literature scan (round {round_num}) could not reach "
                f"arXiv API on {today}. Propose adding a scheduled fetch task "
                "to pull daily abstracts from cs.MS, physics.comp-ph, "
                "astro-ph.IM, nucl-th, physics.plasm-ph."
            ),
            acceptance_criteria=[
                "Daily arXiv scan runs and produces proposals",
                f"Covers categories: {', '.join(ARXIV_CATEGORIES)}",
            ],
            estimated_effort="small",
            estimated_impact="medium",
            evidence=[
                f"scanned_categories:{','.join(ARXIV_CATEGORIES)}",
                f"scan_date:{today}",
                "status:offline_fallback",
                "scanned_by:r7_literature",
            ],
        ),
        Proposal(
            domain="literature",
            title="[arXiv literature] Integrate new numerical methods from cs.MS and physics.comp-ph",
            rationale=(
                "Papers in cs.MS and physics.comp-ph regularly propose new "
                "numerical solvers, discretization schemes, and benchmarks "
                "relevant to the bob scientific computing framework. "
                "Tracking these accelerates feature adoption."
            ),
            acceptance_criteria=[
                "Application spec created for at least one method from recent literature",
                "Benchmark from recent paper integrated into test suite",
            ],
            estimated_effort="medium",
            estimated_impact="high",
            evidence=[
                f"filter_keywords:{','.join(FILTER_KEYWORDS[:5])}",
                f"target_categories:cs.MS,physics.comp-ph",
                "scanned_by:r7_literature",
            ],
        ),
        Proposal(
            domain="literature",
            title="[arXiv literature] Monitor open implementations in astro-ph.IM, nucl-th, physics.plasm-ph",
            rationale=(
                "Astrophysics, nuclear theory, and plasma physics communities "
                "frequently release open-source codes alongside papers. "
                "These represent ready integration candidates for new "
                "application specs in the framework."
            ),
            acceptance_criteria=[
                "At least one open implementation from recent literature evaluated for integration",
            ],
            estimated_effort="small",
            estimated_impact="medium",
            evidence=[
                f"target_categories:astro-ph.IM,nucl-th,physics.plasm-ph",
                "filter:open-source,implementation,code release",
                "scanned_by:r7_literature",
            ],
        ),
    ]


def run(round_num: int) -> list[Proposal]:
    """Pull daily arXiv abstracts, filter for relevant papers, and emit Proposals.

    Scans categories: cs.MS, physics.comp-ph, astro-ph.IM, nucl-th, physics.plasm-ph.
    Filters for papers proposing new methods, benchmarks, or open implementations.
    Returns Proposals suggesting framework features or application specs.
    """
    proposals: list[Proposal] = []
    network_available = False

    for category in ARXIV_CATEGORIES:
        papers = _fetch_arxiv_papers(category)
        if papers:
            network_available = True
        for paper in papers:
            if _paper_matches_filter(paper.get("abstract", "")):
                proposals.append(_paper_to_proposal(paper))

    if not network_available:
        return _generate_offline_proposals(round_num)

    if not proposals:
        # Network was available but no papers matched the filter
        today = datetime.date.today().isoformat()
        proposals.append(
            Proposal(
                domain="literature",
                title=f"[arXiv scan] No new method papers found on {today}",
                rationale=(
                    f"R7 arXiv scan (round {round_num}) on {today} found no papers "
                    "proposing new methods, benchmarks, or open implementations "
                    f"in categories: {', '.join(ARXIV_CATEGORIES)}."
                ),
                acceptance_criteria=["Re-run scan tomorrow"],
                estimated_effort="trivial",
                estimated_impact="low",
                evidence=[
                    f"scanned_categories:{','.join(ARXIV_CATEGORIES)}",
                    f"scan_date:{today}",
                    "filter_result:no_matches",
                    "scanned_by:r7_literature",
                ],
            )
        )

    return proposals
