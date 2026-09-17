import re

import httpx

from app.config import BRAVE_SEARCH_API_KEY, BRAVE_SEARCH_URL, DUCKDUCKGO_URL, SEARCH_TIMEOUT
from app.logging_config import logger


async def search_brave(question: str, request_id: str) -> list:
    """Real web results. Only used when BRAVE_SEARCH_API_KEY is set."""
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            response = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": question, "count": 5, "safesearch": "moderate"},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
                },
            )
            response.raise_for_status()
            items = (response.json().get("web") or {}).get("results") or []
    except Exception as e:
        logger.error("[%s] search=brave_error type=%s", request_id, type(e).__name__)
        return []

    results = []
    for item in items[:5]:
        url = (item.get("url") or "").strip()
        text = re.sub(r"<[^>]+>", "", item.get("description") or "").strip()
        if url.startswith("https://") and text:
            results.append({
                "title": re.sub(r"<[^>]+>", "", item.get("title") or url)[:100],
                "content": text[:500],
                "url": url,
            })
    logger.info("[%s] search=brave results=%d", request_id, len(results))
    return results


async def search_duckduckgo(question: str, request_id: str) -> list:
    """Instant Answer API: encyclopedia abstracts only, no live results."""

    params = {
        "q": question,
        "format": "json",
        "no_redirect": 1,
        "skip_disambig": 1,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                DUCKDUCKGO_URL,
                params=params,
                timeout=SEARCH_TIMEOUT,
            )

            # Handle different response codes (202 is also OK for async responses)
            if response.status_code not in [200, 202]:
                logger.warning(f"[{request_id}] DuckDuckGo returned {response.status_code}")
                return []

            data = response.json()
            cleaned_results = []

            # Try to get abstract result
            abstract_text = data.get("AbstractText", "").strip()
            abstract_url = data.get("AbstractURL", "").strip()

            if abstract_text and abstract_url:
                cleaned_results.append({
                    "title": data.get("Heading", "Search Result")[:100],
                    "content": abstract_text[:500],
                    "url": abstract_url,
                })
                logger.info(f"[{request_id}] Found abstract result from DuckDuckGo")

            # Try to get related topics
            related_topics = data.get("RelatedTopics", [])
            if related_topics:
                for result in related_topics[:3]:
                    if isinstance(result, dict):
                        text = result.get("Text", "").strip()
                        url = result.get("FirstURL", "").strip()

                        if text and url:
                            cleaned_results.append({
                                "title": text[:100],
                                "content": text[:500],
                                "url": url,
                            })

                if cleaned_results:
                    logger.info(f"[{request_id}] Found {len(cleaned_results)} results from DuckDuckGo")

            if not cleaned_results:
                logger.warning(f"[{request_id}] DuckDuckGo returned empty response")

            return cleaned_results

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] DuckDuckGo timeout")
        return []
    except Exception as e:
        logger.error(f"[{request_id}] DuckDuckGo error: {type(e).__name__}: {str(e)}")
        return []


async def search_web(question: str, request_id: str) -> list:
    if BRAVE_SEARCH_API_KEY:
        results = await search_brave(question, request_id)
        if results:
            return results
    return await search_duckduckgo(question, request_id)
