"""
NewsNexus Client - Fetch Top News
A simple client to fetch top news using the NewsNexus MCP server functions.
"""

import json
import sys
from datetime import datetime

# Import the get_top_news function from main.py
# Note: This imports the function directly without starting the MCP server
try:
    # Suppress excessive logging for clean output
    import logging
    logging.getLogger('newsnexus').setLevel(logging.WARNING)
    
    from main import get_top_news, get_articles, get_health
except ImportError as e:
    print(f"Error importing from main.py: {e}")
    print("Make sure main.py is in the same directory and all dependencies are installed.")
    sys.exit(1)


def print_article(article, index):
    """Pretty print a single article."""
    print(f"\n{'='*80}")
    print(f"Article #{index}")
    print(f"{'='*80}")
    print(f"Title:        {article.get('title', 'N/A')}")
    print(f"URL:          {article.get('url', 'N/A')}")
    print(f"Published:    {article.get('published_at', 'N/A')}")
    print(f"Source:       {article.get('source_domain', 'N/A')}")
    
    summary = article.get('summary', '')
    if summary:
        # Truncate summary to 150 characters for readability
        summary_preview = summary[:150] + "..." if len(summary) > 150 else summary
        print(f"Summary:      {summary_preview}")
    
    tags = article.get('tags', [])
    if tags:
        print(f"Tags:         {', '.join(tags[:5])}")  # Show first 5 tags
    
    author = article.get('author', '')
    if author:
        print(f"Author:       {author}")


def main():
    """Main entry point for the fetch top news script."""
    
    print("\n" + "="*80)
    print(" NewsNexus - Top News Fetcher ".center(80, "="))
    print("="*80 + "\n")
    
    # Example 1: Fetch top 10 news articles
    print("📰 Fetching top 10 news articles from priority sources...\n")
    
    try:
        result = get_top_news(count=10)
        
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return
        
        articles = result.get('articles', [])
        sources_used = result.get('sources_used', [])
        total_articles = result.get('total_articles', len(articles))
        duration_ms = result.get('durationMs', 0)
        cached = result.get('cached', False)
        
        # Print summary
        print(f"✅ Successfully fetched {total_articles} articles in {duration_ms:.0f}ms")
        print(f"📦 Cached: {'Yes' if cached else 'No'}")
        print(f"\n📊 Sources Used ({len(sources_used)}):")
        for source_info in sources_used:
            print(f"   • {source_info}")
        
        # Print articles
        print(f"\n📰 Articles ({len(articles)}):")
        for i, article in enumerate(articles, 1):
            print_article(article, i)
        
        # Example 2: Fetch AI-related news
        print("\n\n" + "="*80)
        print(" Example 2: Fetch AI-related news ".center(80, "="))
        print("="*80 + "\n")
        
        print("🤖 Fetching top 5 AI-related news articles...\n")
        ai_result = get_top_news(count=5, topic="AI")
        
        ai_articles = ai_result.get('articles', [])
        print(f"✅ Found {len(ai_articles)} AI-related articles")
        
        for i, article in enumerate(ai_articles, 1):
            print(f"\n{i}. {article.get('title', 'N/A')}")
            print(f"   Source: {article.get('source_domain', 'N/A')}")
            print(f"   URL: {article.get('url', 'N/A')}")
        
        # Example 3: Check server health
        print("\n\n" + "="*80)
        print(" Example 3: Server Health Check ".center(80, "="))
        print("="*80 + "\n")
        
        health = get_health()
        print("🏥 Server Health:")
        print(json.dumps(health, indent=2))
        
        # Save results to file
        output_file = f"news_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'top_news': result,
                'ai_news': ai_result,
                'health': health,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
