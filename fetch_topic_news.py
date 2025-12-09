#!/usr/bin/env python3
"""
Flexible news fetcher for ANY topic with priority domain fallback.
Supports: AI news, Tech news, Cricket news, Finance news, etc.

Usage:
  python fetch_topic_news.py --topic "cricket" --json
  python fetch_topic_news.py --topic "technology" --json
  python fetch_topic_news.py --topic "finance" --json
"""

import sys
import os
import html
import re
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import get_articles

# Global flag to suppress logs when outputting JSON
QUIET_MODE = False

def log(*args, **kwargs):
    """Print only if not in quiet mode."""
    if not QUIET_MODE:
        print(*args, **kwargs)

# Topic keyword mappings
TOPIC_KEYWORDS = {
    'ai': [
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'gpt', 'llm', 'large language model', 'chatgpt', 
        'claude', 'gemini', 'openai', 'anthropic', 'google ai', 'ai model',
        'agent', 'agentic', 'generative ai', 'transformer', 'nlp',
        'natural language', 'computer vision', 'chatbot', 'copilot',
        'ai assistant', 'prompt engineering', 'fine-tuning', 'embedding'
    ],
    'cricket': [
        'cricket', 'ipl', 'test match', 'odi', 't20', 'bcci', 'wicket',
        'batsman', 'bowler', 'innings', 'stumps', 'run', 'six', 'four',
        'cricket world cup', 'cricket match', 'virat kohli', 'rohit sharma',
        'ms dhoni', 'cricket series', 'cricketer', 'cricket team'
    ],
    'tech': [
        'technology', 'tech', 'software', 'hardware', 'startup', 'gadget',
        'smartphone', 'laptop', 'cloud', 'cyber', 'programming', 'developer',
        'app', 'web', 'digital', 'innovation', 'tech industry', 'tech news',
        'blockchain', 'crypto', 'metaverse', 'virtual reality'
    ],
    'finance': [
        'finance', 'stock', 'market', 'investment', 'banking', 'rupee',
        'dollar', 'share', 'sensex', 'nifty', 'portfolio', 'mutual fund',
        'dividend', 'ipo', 'trading', 'financial', 'economy', 'economics',
        'fiscal', 'budget', 'commodity', 'gold', 'silver'
    ],
    'sports': [
        'sports', 'cricket', 'football', 'soccer', 'tennis', 'badminton',
        'hockey', 'basketball', 'volleyball', 'athlete', 'tournament',
        'championship', 'medal', 'olympics', 'match', 'game', 'team',
        'player', 'coach', 'sport news'
    ],
    'politics': [
        'politics', 'election', 'parliament', 'government', 'minister',
        'political', 'policy', 'vote', 'democracy', 'law', 'bill',
        'state', 'national', 'congress', 'bjp', 'political party',
        'election commission', 'lok sabha', 'rajya sabha'
    ],
    'health': [
        'health', 'medical', 'doctor', 'hospital', 'disease', 'vaccine',
        'covid', 'pandemic', 'wellness', 'fitness', 'nutrition', 'medicine',
        'health news', 'healthcare', 'virus', 'treatment', 'patient',
        'symptom', 'disease outbreak'
    ],
    'entertainment': [
        'entertainment', 'movie', 'film', 'cinema', 'bollywood', 'hollywood',
        'actor', 'actress', 'celebrity', 'music', 'concert', 'album',
        'netflix', 'amazon prime', 'ott', 'web series', 'tv show',
        'box office', 'premiere', 'trailer', 'award', 'oscar', 'grammy'
    ],
    'education': [
        'education', 'school', 'college', 'university', 'student', 'teacher',
        'exam', 'admission', 'scholarship', 'degree', 'course', 'learning',
        'neet', 'jee', 'upsc', 'cbse', 'icse', 'academic', 'graduation',
        'entrance exam', 'study', 'curriculum'
    ]
}

EXCLUDE_KEYWORDS = [
    'ukraine', 'russia', 'war', 'paint', 'painter', 'painting'
]

def is_topic_related(article, topic_keywords):
    """Check if article is related to the given topic using word boundaries."""
    if not article:
        return False
    
    title = article.get('title', '').lower()
    description = article.get('description', '').lower()
    text = title + ' ' + description
    
    # Check if any topic keyword appears with word boundaries
    for keyword in topic_keywords:
        if re.search(r'\b' + re.escape(keyword) + r'\b', text):
            # Check if it's not an excluded keyword
            for exclude in EXCLUDE_KEYWORDS:
                if re.search(r'\b' + re.escape(exclude) + r'\b', text):
                    return False
            return True
    
    return False

def fetch_from_priority_domains(topic_keywords, limit=8):
    """Fetch from priority domains only."""
    log(f"Fetching from priority domains...")
    
    # Load priority domains from sites.json
    import json
    with open('sites.json', 'r') as f:
        sites_list = json.load(f)
    
    priority_domains = [
        site['domain'] for site in sites_list
        if site.get('priority', 999) <= 3
    ][:10]  # Limit to 10 priority domains
    
    all_articles = []
    for domain in priority_domains:
        result = get_articles(domain, count=limit * 3)
        if result.get('articles'):
            all_articles.extend(result['articles'])
    
    filtered = [
        article for article in all_articles
        if is_topic_related(article, topic_keywords)
    ][:limit]
    
    log(f"Got {len(filtered)} relevant articles from priority domains")
    return filtered

def fetch_from_nonpriority_fallback(topic_keywords, limit=8):
    """Fallback to non-priority domains if priority insufficient."""
    log(f"Priority domains insufficient, fetching from fallback sources...")
    
    # Load non-priority domains from sites.json
    import json
    with open('sites.json', 'r') as f:
        sites_list = json.load(f)
    
    nonpriority_domains = [
        site['domain'] for site in sites_list
        if site.get('priority', 999) > 3
    ][:10]  # Limit to 10 fallback domains
    
    all_articles = []
    for domain in nonpriority_domains:
        result = get_articles(domain, count=limit * 3)
        if result.get('articles'):
            all_articles.extend(result['articles'])
    
    filtered = [
        article for article in all_articles
        if is_topic_related(article, topic_keywords)
    ][:limit]
    
    log(f"Got {len(filtered)} relevant articles from fallback sources")
    return filtered

def fetch_topic_news(topic, limit=8):
    """Main function to fetch news for any topic."""
    topic_lower = topic.lower().strip()
    
    # Get keywords for the topic
    if topic_lower not in TOPIC_KEYWORDS:
        available_topics = ', '.join(TOPIC_KEYWORDS.keys())
        log(f"ERROR: Topic '{topic}' not found.")
        log(f"Available topics: {available_topics}")
        return []
    
    keywords = TOPIC_KEYWORDS[topic_lower]
    log(f"\nFetching {topic.upper()} news...")
    log(f"Keywords: {', '.join(keywords[:5])}... (+{len(keywords)-5} more)")
    
    # Try priority domains first
    articles = fetch_from_priority_domains(keywords, limit)
    
    # If we don't have enough, use fallback
    if len(articles) < limit:
        remaining_needed = limit - len(articles)
        fallback_articles = fetch_from_nonpriority_fallback(keywords, remaining_needed)
        articles.extend(fallback_articles)
    
    return articles[:limit]

def main():
    parser = argparse.ArgumentParser(
        description='Fetch news for any topic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python fetch_topic_news.py --topic cricket --json
  python fetch_topic_news.py --topic "technology" --json
  python fetch_topic_news.py --topic sports

Available topics: {', '.join(TOPIC_KEYWORDS.keys())}
        """
    )
    parser.add_argument('--topic', type=str, default='ai',
                       help='Topic to fetch news for (default: ai)')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--limit', type=int, default=8,
                       help='Number of articles to fetch (default: 8)')
    
    args = parser.parse_args()
    
    # Set quiet mode if JSON output
    global QUIET_MODE
    if args.json:
        QUIET_MODE = True
    
    articles = fetch_topic_news(args.topic, args.limit)
    
    if args.json:
        print(json.dumps(articles, indent=2, ensure_ascii=False))
    else:
        if not articles:
            print(f"No articles found for topic: {args.topic}")
        else:
            print(f"\n{'='*80}")
            print(f"TOP {len(articles)} {args.topic.upper()} NEWS")
            print(f"{'='*80}\n")
            for i, article in enumerate(articles, 1):
                print(f"{i}. {article.get('title', 'No Title')}")
                print(f"   Source: {article.get('source', 'Unknown')}")
                print(f"   {article.get('description', 'No description')[:150]}...")
                print()

if __name__ == '__main__':
    main()
