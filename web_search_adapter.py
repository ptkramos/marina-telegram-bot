"""The project's single bounded DDGS text-search adapter."""


def search_text(query: str, *, max_results: int = 3, timeout: int = 4) -> list[dict]:
    from ddgs import DDGS

    return list(DDGS(timeout=timeout).text(query, max_results=max_results, region='br-pt'))
