# NewsNexus Filtering Guide

## Overview
NewsNexus supports **5 types of filtering** to help you find exactly the news you need:

1. **Topic-based Filtering** - Filter by keywords
2. **Location-based Filtering** - Filter by geography
3. **Time-based Filtering** - Filter by date range
4. **Deduplication** - Automatic removal of duplicates (always active)
5. **Priority-based Site Filtering** - Fetch from top-priority sources (always active)

## Built-in Features (Always Active)

### Deduplication
NewsNexus automatically removes duplicate articles using:
- **URL deduplication**: Removes articles with identical URLs
- **Title deduplication**: Removes articles with identical titles (case-insensitive, whitespace-normalized)

### Priority-based Site Filtering
- Fetches from top 12 priority sites only (sites with priority 1-12)
- Sites with `null` priority are excluded from top news
- Parallel fetching from 8 workers for optimal speed
- Response time: 2-3 seconds typically

## Command-Line Filtering

### 1. Topic Filter (`--topic`)
Filter articles by keywords in title, summary, or tags.

**Examples:**
```bash
# AI-related news
python fetch_news.py --count 5 --topic AI

# Artificial intelligence (more specific)
python fetch_news.py --count 5 --topic "artificial intelligence"

# Technology news
python fetch_news.py --count 10 --topic technology

# Sports news
python fetch_news.py --count 10 --topic sports
```

### 2. Location Filter (`--location`)
Filter articles by geographic keywords.

**Examples:**
```bash
# India-specific news
python fetch_news.py --count 10 --location India

# Mumbai-specific news
python fetch_news.py --count 5 --location Mumbai

# USA news
python fetch_news.py --count 10 --location USA
```

### 3. Time-based Filter (`--days`)
Fetch articles from the last N days.

**Examples:**
```bash
# Today's news only (default)
python fetch_news.py --count 10

# Last 2 days
python fetch_news.py --count 10 --days 2

# Last week
python fetch_news.py --count 20 --days 7

# Last 30 days
python fetch_news.py --count 50 --days 30
```

### 4. Combined Filters
Combine multiple filters for precise results.

**Examples:**
```bash
# AI news from India, last 3 days
python fetch_news.py --count 5 --topic AI --location India --days 3

# Technology news from last week with 2-line summaries
python fetch_news.py --count 15 --topic technology --days 7 --summary_lines 2

# Sports news from today only
python fetch_news.py --count 10 --topic sports --location India --days 1
```

## MCP Server Filtering (API)

If you're using the MCP server directly, you can pass these parameters:

```json
{
  "name": "get_top_news",
  "arguments": {
    "count": 10,
    "topic": "AI",
    "location": "India",
    "lastNDays": 3
  }
}
```

## Performance Notes

- **Optimal count**: 10-20 articles for best speed
- **Response time**: 2-3 seconds typical, up to 10 seconds for complex queries
- **Deduplication**: Always active, no performance impact
- **Priority sites**: Only 8-12 sites fetched in parallel
- **Timeout**: 2 seconds per source, 1 retry per source

## Tips for Best Results

1. **Be specific with topics**: Use "artificial intelligence" instead of just "AI" for more relevant results
2. **Combine filters**: Topic + Location + Days gives most precise results
3. **Adjust days based on topic**: 
   - Breaking news: `--days 1`
   - Trending topics: `--days 3-7`
   - Research/analysis: `--days 30`
4. **Use summary_lines**: Adjust between 1-5 based on how much detail you need

## Filter Matching Logic

- **Case-insensitive**: All filters are case-insensitive
- **Substring matching**: Filters match any part of title, summary, or tags
- **AND logic**: Multiple filters are combined with AND (all must match)
- **Sanitized input**: Special characters are handled safely

## Examples by Use Case

### Daily News Briefing
```bash
python fetch_news.py --count 10 --days 1
```

### Tech Industry Updates
```bash
python fetch_news.py --count 15 --topic technology --days 3
```

### AI Research & News
```bash
python fetch_news.py --count 20 --topic "artificial intelligence" --days 7 --summary_lines 4
```

### Local News
```bash
python fetch_news.py --count 10 --location India --days 1
```

### Specific Topic + Region
```bash
python fetch_news.py --count 10 --topic startup --location India --days 5
```
