#!/usr/bin/env python3
"""
CORRECTED: Fetch AI news with proper FALLBACK mechanism

Architecture:
1. Priority Sites (priority: 1-3) with their internal source hierarchy
2. For each priority site:
   - Try source_priority 1 (Official RSS) first
   - Fallback to source_priority 2 (Google News)
   - Fallback to source_priority 3 (Web Scraper)
3. Only move to NON-PRIORITY sites if priority sites exhausted

This respects the NewsNexus framework's design:
- Multiple feeds from same domain (official RSS → Google → Scraper)
- Priority site ordering (1, 2, 3...)
- Topic filtering (AI keyword matching)
"""

import sys
import os
import html
import re
import json
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

# AI keyword matching
AI_KEYWORDS = [
    'ai', 'artificial intelligence', 'machine learning', 'deep learning',
    'neural network', 'gpt', 'llm', 'large language model', 'chatgpt', 
    'claude', 'gemini', 'openai', 'anthropic', 'google ai', 'ai model',
    'agent', 'agentic', 'generative ai', 'transformer', 'nlp',
    'natural language', 'computer vision', 'chatbot', 'copilot',
    'ai assistant', 'prompt engineering', 'fine-tuning', 'embedding'
]

EXCLUDE_KEYWORDS = [
    'gaming', 'skateboard', 'console', 'n64', 'tv show', 'movie',
    'music', 'fashion', 'sports', 'football', 'basketball', 'cricket'
]


def is_ai_related(article):
    """Check if article is AI-related with word boundary matching."""
    title = article.get('title', '').lower()
    summary = article.get('summary', '').lower()
    combined = title + ' ' + summary
    
    # Exclude non-AI content (word boundary matching)
    for keyword in EXCLUDE_KEYWORDS:
        if re.search(r'\b' + re.escape(keyword) + r'\b', combined):
            return False
    
    # Check for AI keywords (word boundary matching)
    for keyword in AI_KEYWORDS:
        if re.search(r'\b' + re.escape(keyword) + r'\b', combined):
            return True
    
    return False


def fetch_from_priority_domains(count=8, days=7):
    """
    CORRECT APPROACH: Fetch AI news from PRIORITY domains with proper fallback
    
    Priority domains (in order):
    1. NDTV (priority: 1)
    2. Indian Express (priority: 2) ← HAS AI FEED
    3. Times of India (priority: 3)
    4. Hindustan Times (priority: 4)
    5. Gadgets360 (priority: 5)
    6. Economic Times (priority: 6) ← HAS AI FEED
    
    For each domain, use source_priority fallback:
    - Priority 1: Official RSS (best)
    - Priority 2: Google News (fallback)
    - Priority 3: Web Scraper (last resort)
    """
    
    log("\n" + "="*140)
    log("🔍 FETCHING AI NEWS - RESPECTING PRIORITY LIST WITH FALLBACK".center(140))
    log("="*140 + "\n")
    
    # Priority domains in order (from sites.json)
    priority_domains = [
        ('ndtv.com', 1),
        ('indianexpress.com', 2),  # Has AI feed
        ('timesofindia.indiatimes.com', 3),
        ('hindustantimes.com', 4),
        ('gadgets360.com', 5),
        ('economictimes.indiatimes.com', 6),  # Has AI feed
    ]
    
    all_articles = []
    sources_tried = []
    
    log(f"📋 PRIORITY DOMAINS (checking in order):\n")
    for domain, p in priority_domains:
        log(f"  {p}. {domain}")
    
    log(f"\n{'='*140}")
    log(f"⬇️  FETCHING FROM PRIORITY DOMAINS (with source priority fallback)".center(140))
    log(f"{'='*140}\n")
    
    # Fetch from each priority domain
    for domain, priority in priority_domains:
        log(f"\n🔄 Domain: {domain} (priority: {priority})")
        log("-" * 140)
        
        domain_articles = []
        
        try:
            # Try to fetch with topic filter (uses source_priority 1, 2, 3 internally)
            # get_articles() automatically tries source_priority 1 → 2 → 3
            result = get_articles(
                domain=domain,
                topic="AI",  # Filter for AI content
                count=count,
                lastNDays=days
            )
            
            if result and 'articles' in result:
                articles = result['articles']
                
                # Additional keyword filtering for accuracy
                ai_articles = [a for a in articles if is_ai_related(a)]
                
                log(f"  ✅ Retrieved {len(articles)} articles, {len(ai_articles)} AI-related")
                
                if ai_articles:
                    domain_articles.extend(ai_articles)
                    all_articles.extend(ai_articles)
                    sources_tried.append({
                        'domain': domain,
                        'priority': priority,
                        'count': len(ai_articles),
                        'status': 'success'
                    })
                else:
                    log(f"  ⚠️  No AI-related articles found")
                    sources_tried.append({
                        'domain': domain,
                        'priority': priority,
                        'count': 0,
                        'status': 'no_ai'
                    })
            else:
                log(f"  ⚠️  No articles returned")
                sources_tried.append({
                    'domain': domain,
                    'priority': priority,
                    'count': 0,
                    'status': 'empty'
                })
                
        except Exception as e:
            log(f"  ❌ Error: {str(e)[:80]}")
            sources_tried.append({
                'domain': domain,
                'priority': priority,
                'count': 0,
                'status': f'error: {str(e)[:40]}'
            })
    
    # Remove duplicates
    unique_articles = deduplicate_articles(all_articles)
    
    # Sort by date (handle None values)
    unique_articles.sort(key=lambda x: x.get('published_at') or '1970-01-01', reverse=True)
    
    final_articles = unique_articles[:count]
    
    log(f"\n{'='*140}")
    log(f"📊 RESULTS FROM PRIORITY SOURCES".center(140))
    log(f"{'='*140}\n")
    
    # Show summary
    total_from_priority = sum(s['count'] for s in sources_tried)
    log(f"Total AI articles from priority sources: {total_from_priority}")
    log(f"After deduplication: {len(unique_articles)}")
    log(f"Final result: {len(final_articles)}/{count}\n")
    
    # Show sources
    log(f"{'Domain':<35} {'Priority':<10} {'Status':<20} {'Count'}")
    log("-" * 140)
    for source in sources_tried:
        log(f"{source['domain']:<35} {source['priority']:<10} {source['status']:<20} {source['count']}")
    
    return final_articles, unique_articles, sources_tried


def fetch_from_nonpriority_fallback(existing_count=0, target_count=8, days=7):
    """
    FALLBACK: Only use non-priority sources if priority sources insufficient
    
    Non-priority tech sources:
    - TechCrunch
    - VentureBeat
    - OpenAI
    - The Verge
    - Wired
    - ArsT
    """
    
    if existing_count >= target_count:
        log(f"\n✅ Already have {existing_count} articles, no fallback needed")
        return []
    
    needed = target_count - existing_count
    
    log(f"\n{'='*140}")
    log(f"⚠️  INSUFFICIENT FROM PRIORITY ({existing_count}/{target_count})".center(140))
    log(f"{'='*140}\n")
    log(f"📍 FALLBACK: Fetching {needed} more from NON-PRIORITY tech sources\n")
    
    nonpriority_domains = [
        'techcrunch.com',
        'venturebeat.com',
        'openai.com',
        'theverge.com',
        'wired.com',
        'arstechnica.com'
    ]
    
    all_articles = []
    sources_tried = []
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(get_articles, domain=domain, lastNDays=days, count=needed):
            domain for domain in nonpriority_domains
        }
        
        for future in as_completed(futures):
            domain = futures[future]
            try:
                result = future.result(timeout=5)
                if result and 'articles' in result:
                    articles = result['articles']
                    ai_articles = [a for a in articles if is_ai_related(a)]
                    
                    log(f"  ✅ {domain}: {len(ai_articles)} AI articles")
                    all_articles.extend(ai_articles)
                    sources_tried.append({'domain': domain, 'count': len(ai_articles)})
                else:
                    log(f"  ⚠️  {domain}: 0 articles")
            except Exception as e:
                log(f"  ❌ {domain}: {str(e)[:50]}")
    
    # Deduplicate and return
    unique = deduplicate_articles(all_articles)
    unique.sort(key=lambda x: x.get('published_at', ''), reverse=True)
    
    return unique[:needed]


def deduplicate_articles(articles):
    """Remove duplicate articles by URL."""
    seen_urls = set()
    unique = []
    
    for article in articles:
        url = article.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(article)
    
    return unique


def display_articles(articles, source_type="COMBINED"):
    """Display articles in readable format."""
    log(f"\n{'='*140}")
    log(f"📰 FINAL RESULT: TOP {len(articles)} AI NEWS ({source_type})".center(140))
    log(f"{'='*140}\n")
    
    for idx, article in enumerate(articles[:10], 1):
        title = html.unescape(article.get('title', 'No title'))
        url = article.get('url', 'No URL')
        date = article.get('published_at', 'No date')
        source = article.get('source_domain', 'Unknown')
        summary = article.get('summary', 'No summary')
        
        # Decode HTML and clean
        if summary:
            summary = html.unescape(summary)
            summary = re.sub(r'<[^>]+>', '', summary)
            if len(summary) > 300:
                summary = summary[:297] + '...'
        
        log(f"{idx}. {title}")
        log(f"   🔗 {url}")
        log(f"   📅 {date} | 🏢 {source}")
        log(f"   📝 {summary}\n")


def main():
    """Main function with proper fallback flow."""
    
    global QUIET_MODE
    import argparse
    parser = argparse.ArgumentParser(description="Fetch top AI news with proper fallback.")
    parser.add_argument('--json', action='store_true', help='Output raw JSON of articles')
    parser.add_argument('--count', type=int, default=8, help='Number of articles to fetch')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back')
    args = parser.parse_args()

    # Enable quiet mode if JSON output is requested
    if args.json:
        QUIET_MODE = True

    target_count = args.count
    days = args.days

    # STEP 1: Fetch from PRIORITY sources with fallback
    priority_articles, all_from_priority, sources_tried = fetch_from_priority_domains(
        count=target_count,
        days=days
    )

    priority_count = len(priority_articles)

    # STEP 2: If insufficient, fallback to non-priority
    if priority_count < target_count:
        fallback_articles = fetch_from_nonpriority_fallback(
            existing_count=priority_count,
            target_count=target_count,
            days=days
        )
        final_articles = priority_articles + fallback_articles
        final_articles = deduplicate_articles(final_articles)
        final_articles.sort(key=lambda x: x.get('published_at', ''), reverse=True)
        final_articles = final_articles[:target_count]
        source_type = f"PRIORITY ({priority_count}) + NON-PRIORITY ({len(fallback_articles)})"
    else:
        final_articles = priority_articles
        source_type = "PRIORITY"

    if args.json:
        print(json.dumps(final_articles, indent=2, ensure_ascii=False))
    else:
        display_articles(final_articles, source_type)
        log(f"\n{'='*140}")
        log(f"✅ SUMMARY".center(140))
        log(f"{'='*140}\n")
        log(f"Total articles fetched: {len(final_articles)}")
        log(f"Source: {source_type}")
        log(f"From priority sites: {priority_count}")
        if priority_count < target_count:
            log(f"From fallback sources: {len(final_articles) - priority_count}")
        log(f"\n{'='*140}\n")


if __name__ == '__main__':
    main()
