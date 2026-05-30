"""
Test rápido del WebSearchAgent — sin MemPalace ni Anthropic key requerida.
Verifica: DuckDuckGo, RSS, y el contexto por defecto.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.web_search_agent import WebSearchAgent, NewsItem


def test_duckduckgo():
    agent = WebSearchAgent(memory_client=None, llm_client=None)
    results = agent.search_duckduckgo("Bitcoin price news", max_results=3)
    assert len(results) > 0, "DuckDuckGo no retornó resultados"
    assert isinstance(results[0], NewsItem)
    assert results[0].title != ""
    print(f"  DuckDuckGo OK — {len(results)} noticias")
    for r in results:
        print(f"    [{r.source}] {r.title[:60]}")


def test_rss():
    agent = WebSearchAgent(memory_client=None, llm_client=None)
    results = agent.fetch_rss("https://cointelegraph.com/rss", max_items=3)
    assert len(results) > 0, "RSS no retornó artículos"
    print(f"  RSS OK — {len(results)} artículos de CoinTelegraph")
    for r in results:
        print(f"    {r.title[:60]}")


def test_default_context():
    agent = WebSearchAgent(memory_client=None, llm_client=None)
    ctx = agent.get_latest_context()
    assert "overall_sentiment" in ctx
    assert "avoid_trading" in ctx
    assert "recommended_asset" in ctx
    print(f"  Default context OK — asset: {ctx['recommended_asset']}, avoid: {ctx['avoid_trading']}")


if __name__ == "__main__":
    print("\n=== Test WebSearchAgent ===\n")

    print("[1] DuckDuckGo search...")
    test_duckduckgo()

    print("\n[2] RSS feed...")
    test_rss()

    print("\n[3] Default context...")
    test_default_context()

    print("\nTodos los tests OK")
