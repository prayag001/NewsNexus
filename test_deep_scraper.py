"""
Test script for deep scraper functionality.
"""
import requests
from main import parse_html_scraper_deep, DEEP_SCRAPE_MAX_ARTICLES, DEEP_SCRAPE_ENABLED, USER_AGENT

def test_deep_scraper():
    # Test with TechCrunch - has good article structure
    url = 'https://techcrunch.com/'
    domain = 'techcrunch.com'
    
    print(f'Testing deep scraper with: {url}')
    print(f'Deep scrape enabled: {DEEP_SCRAPE_ENABLED}')
    print(f'Max articles to deep scrape: {DEEP_SCRAPE_MAX_ARTICLES}')
    print()

    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, timeout=10, headers=headers)
        print(f'Response status: {response.status_code}')
        
        if response.status_code == 200:
            articles = parse_html_scraper_deep(
                response.content, 
                domain, 
                url, 
                enable_deep_scrape=True
            )
            print(f'Found {len(articles)} articles total')
            print()
            
            for i, art in enumerate(articles[:5]):
                print(f'--- Article {i+1} ---')
                title = art.get('title', 'N/A')
                print(f"Title: {title[:100] if title else 'N/A'}")
                
                article_url = art.get('url', 'N/A')
                print(f"URL: {article_url[:100] if article_url else 'N/A'}")
                
                print(f"Deep scraped: {art.get('deep_scraped', False)}")
                print(f"Content length: {art.get('content_length', 0)} chars")
                print(f"Published: {art.get('published_at', 'Unknown')}")
                print(f"Author: {art.get('author', 'Unknown')}")
                
                summary = art.get('summary', '')
                if summary:
                    print(f"Summary: {summary[:250]}...")
                print()
        else:
            print(f'Failed to fetch: {response.status_code}')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_deep_scraper()
