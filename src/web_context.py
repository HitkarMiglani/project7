"""
src/web_context.py
Fetches public company/role context from the web to enrich tailoring.
Uses Brave Search API if available, falls back to basic HTTP.
"""

import os
import re
import httpx
from typing import Optional

from src.logger import get_logger

logger = get_logger("web_context")


def _clean_text(text: str, max_chars: int = 3000) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def fetch_brave_search(query: str, num_results: int = 3) -> str:
    """Query Brave Search API for company/role context."""
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        logger.debug("Brave search skipped: BRAVE_API_KEY not set")
        return ""

    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            params={"q": query, "count": num_results},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        snippets = []
        for result in data.get("web", {}).get("results", []):
            title = result.get("title", "")
            desc = result.get("description", "")
            if title or desc:
                snippets.append(f"- {title}: {desc}")
        logger.info("Brave search returned %d snippets for query=%r", len(snippets), query[:60])
        return "\n".join(snippets)
    except Exception as e:
        logger.warning("Brave search failed: %s", e)
        return ""


def fetch_company_context(job_description: str, job_url: str = "") -> str:
    """
    Extract company name from JD and fetch public context.
    Returns a summary string to inject into the AI prompt.
    """
    context_parts = []

    # Try to get context from job URL page
    if job_url:
        try:
            logger.info("Fetching company context from URL=%s", job_url[:120])
            resp = httpx.get(job_url, timeout=10, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                # Strip HTML tags roughly
                text = re.sub(r"<[^>]+>", " ", resp.text)
                text = _clean_text(text, 2000)
                context_parts.append(f"Job posting content:\n{text}")
        except Exception as e:
            logger.warning("URL fetch failed during context building: %s", e)

    # Try Brave search for company info
    # Extract likely company name from JD (first proper noun sequence)
    company_match = re.search(
        r"(?:at|@|for|with|join)\s+([A-Z][A-Za-z0-9&\s]{2,40}?)(?:\s*[,.]|\s+is\b|\s+we\b)",
        job_description,
    )
    if company_match:
        company_name = company_match.group(1).strip()
        search_result = fetch_brave_search(f"{company_name} company culture mission values")
        if search_result:
            context_parts.append(f"Company context for {company_name}:\n{search_result}")

    result = "\n\n".join(context_parts) if context_parts else "No additional web context available."
    logger.info("Company context built: %d chars", len(result))
    return result
