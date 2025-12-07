#!/usr/bin/env python3
"""
NewsNexus CLI - Advanced News Aggregator with Multi-Layer Filtering

Features:
- Topic-based filtering: Filter by keywords (AI, technology, sports, etc.)
- Location-based filtering: Filter by geography (India, Mumbai, USA, etc.)
- Time-based filtering: Fetch articles from last N days
- Deduplication: Automatic removal of duplicate articles by URL and title
- Priority-based fetching: Fetches from top-priority news sources
- Fast response: Optimized parallel fetching with 2-3 second response time

Examples:
  python fetch_news.py --count 10 --topic AI --days 2
  python fetch_news.py --count 5 --location India --topic technology
  python fetch_news.py --count 20 --days 7 --summary_lines 5
"""
import subprocess
import json
import sys
from datetime import datetime

def fetch_top_news(count=10, summary_lines=3, topic=None, location=None, last_n_days=1):
    """Fetch top news using the MCP server with filtering options."""
    
    # Start the MCP server process
    process = subprocess.Popen(
        [sys.executable, 'main.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1
    )
    
    # Initialize the server
    init_request = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'cli', 'version': '1.0'}
        }
    })
    
    # Fetch top news
    arguments = {
        'count': count,
        'lastNDays': last_n_days
    }
    if topic:
        arguments['topic'] = topic
    if location:
        arguments['location'] = location
    
    news_request = json.dumps({
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'tools/call',
        'params': {
            'name': 'get_top_news',
            'arguments': arguments
        }
    })
    
    # Send requests
    try:
        stdout, stderr = process.communicate(init_request + '\n' + news_request + '\n', timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        print("Error: Request timed out", file=sys.stderr)
        return
    
    if not stdout:
        print("Error: No response from server", file=sys.stderr)
        return
    
    # Parse responses
    lines = stdout.strip().split('\n')
    
    for line in lines:
        if not line:
            continue
        try:
            response = json.loads(line)
            if response.get('id') == 2 and 'result' in response:
                result = response['result']
                if 'content' in result and result['content']:
                    data = json.loads(result['content'][0]['text'])
                    
                    # Display results
                    print("\n" + "="*80)
                    filters = []
                    if topic:
                        filters.append(f"Topic: {topic.upper()}")
                    if location:
                        filters.append(f"Location: {location.upper()}")
                    if last_n_days and last_n_days != 1:
                        filters.append(f"Last {last_n_days} days")
                    filter_text = f" ({', '.join(filters)})" if filters else ""
                    print(f"TOP {count} NEWS{filter_text} - {datetime.now().strftime('%B %d, %Y')}")
                    print("="*80 + "\n")
                    
                    articles = data.get('articles', [])
                    
                    if not articles:
                        print("No articles found.")
                        return
                    
                    for idx, article in enumerate(articles[:count], 1):
                        print(f"{idx}. {article.get('title', 'No title')}")
                        print(f"   Date: {article.get('published_at', 'Unknown')}")
                        
                        summary = article.get('summary', article.get('description', 'No summary'))
                        if summary:
                            # Limit summary to specified lines
                            lines = summary.split('. ')
                            short_summary = '. '.join(lines[:summary_lines])
                            if len(lines) > summary_lines:
                                short_summary += '...'
                            print(f"   Summary: {short_summary}")
                        
                        print(f"   Link: {article.get('url', 'No link')}")
                        print()
                    
                    print(f"Total articles fetched: {data.get('totalFetched', 0)}")
                    print(f"Sources queried: {data.get('sourcesQueried', 0)}")
                    print(f"Duration: {data.get('durationMs', 0):.2f}ms")
                    print("="*80)
                    
        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"Error parsing response: {e}", file=sys.stderr)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch top news with advanced filtering')
    parser.add_argument('--count', type=int, default=10, help='Number of articles to fetch (default: 10)')
    parser.add_argument('--summary_lines', type=int, default=3, help='Number of summary lines (default: 3)')
    parser.add_argument('--topic', type=str, default=None, help='Filter by topic (e.g., AI, technology, sports)')
    parser.add_argument('--location', type=str, default=None, help='Filter by location (e.g., India, Mumbai, USA)')
    parser.add_argument('--days', type=int, default=1, help='Fetch articles from last N days (default: 1 = today only)')
    
    args = parser.parse_args()
    
    try:
        fetch_top_news(args.count, args.summary_lines, args.topic, args.location, args.days)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
