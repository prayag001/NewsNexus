# Domain Filtering Feature - User Guide

## Overview

You can now fetch news from **specific domains only** by providing domain names at runtime. No need to change any configuration - just pass the `domains` parameter!

## How It Works

### Fuzzy Domain Matching

The system uses **intelligent fuzzy matching** to find domains in `sites.json`:

- Partial names work: `'wired'` matches `'wired.com'`
- Case insensitive: `'WIRED'`, `'Wired'`, `'wired'` all work
- Handles spaces: `'analytics vidhya'` matches `'analyticsvidhya.com'`
- Matches domain or site name: `'verge'` matches `'theverge.com'`

## Usage Examples

### Basic Usage

```python
# Fetch from Wired, The Verge, TechRadar only
get_top_news(
    count=8,
    domains=['wired', 'verge', 'techradar']
)
```

### Tech Specialist Sites

```python
# Fetch from AI/ML specialist sites
get_top_news(
    count=10,
    domains=[
        'analytics vidhya',
        'kdnuggets', 
        'infoworld',
        'techrepublic'
    ]
)
```

### Combine with Topic Filter

```python
# Mobile news from specific sites only
get_top_news(
    count=8,
    topic='mobile',
    domains=['wired', 'verge', 'techradar'],
    min_quality_score=40
)
```

### Combine with Quality Filter

```python
# High-quality AI news from specific sites
get_top_news(
    count=10,
    topic='ai',
    domains=['wired', 'verge', 'techcrunch'],
    min_quality_score=45
)
```

## Domain Matching Examples

| Your Input | Matches | Domain |
|------------|---------|--------|
| `'wired'` | ✅ | wired.com |
| `'verge'` | ✅ | theverge.com |
| `'techradar'` | ✅ | techradar.com |
| `'tech radar'` | ✅ | techradar.com |
| `'analytics vidhya'` | ✅ | analyticsvidhya.com |
| `'kdnuggets'` | ✅ | kdnuggets.com |
| `'infoworld'` | ✅ | infoworld.com |
| `'techcrunch'` | ✅ | techcrunch.com |
| `'techrepublic'` | ✅ | techrepublic.com |
| `'tech'` | ✅ | Multiple (techradar, techrepublic, techcrunch, etc.) |

## Features

### ✅ **Runtime Configuration**
- No hardcoded domains
- Provide any domain names at runtime
- Change domains per request

### ✅ **Fuzzy Matching**
- Partial names work
- Case insensitive
- Handles spaces in names

### ✅ **Works with All Filters**
- Combine with `topic` filter
- Combine with `location` filter
- Combine with quality filtering
- Combine with date filtering

### ✅ **Non-Breaking**
- When `domains` not provided, uses existing priority-based logic
- Fully backward compatible

## Comparison

### Without Domain Filter (Default)
```python
# Fetches from top 12 priority sites
# Expands to 20 sites if needed (deep search)
get_top_news(count=8)
```

### With Domain Filter
```python
# Fetches from specified sites only
# No deep search (uses only matched domains)
get_top_news(count=8, domains=['wired', 'verge'])
```

## Response Format

```json
{
  "articles": [
    {
      "heading": "Article title",
      "summary": "Article summary",
      "date": "2025-12-27T10:00:00Z",
      "source_link": "https://...",
      "quality_score": 75.5
    }
  ],
  "total": 8,
  "durationMs": 3245.67,
  "qualityFilterEnabled": true,
  "minQualityScore": 35.0
}
```

## Error Handling

### No Matching Domains

```python
result = get_top_news(count=8, domains=['nonexistent'])
# Returns:
{
  "articles": [],
  "total": 0,
  "durationMs": 0,
  "error": "No sites found matching: nonexistent"
}
```

## Performance

### Speed
- **Faster** than default when fetching from few domains
- **Same quality filtering** applies
- **No deep search** when domains specified

### Examples
```
Default (12 sites):     3-5 seconds
Default (20 sites):     5-8 seconds (with deep search)
Domains (3 sites):      1-2 seconds ⚡
Domains (5 sites):      2-3 seconds ⚡
```

## Tips

### ✅ **Do's**
- Use partial names: `'wired'` instead of `'wired.com'`
- Combine with quality filter for best results
- Use for focused news from specific sources
- Provide runtime domains - nothing hardcoded

### ❌ **Don'ts**
- Don't use full URLs (use domain names only)
- Don't hardcode domains in code
- Don't expect deep search with domain filter

## Real-World Examples

### Example 1: Tech News from Premium Sites
```python
get_top_news(
    count=10,
    topic='tech',
    domains=['wired', 'verge', 'techcrunch'],
    min_quality_score=40
)
```

### Example 2: AI News from Specialist Sites
```python
get_top_news(
    count=8,
    topic='ai',
    domains=['analytics vidhya', 'kdnuggets', 'infoworld'],
    min_quality_score=45
)
```

### Example 3: Mobile Reviews from Tech Sites
```python
get_top_news(
    count=5,
    topic='mobile',
    domains=['techradar', 'verge', 'wired'],
    lastNDays=7
)
```

### Example 4: Latest Laptop News
```python
get_top_news(
    count=8,
    topic='laptop',
    domains=['techrepublic', 'infoworld', 'techradar'],
    lastNDays=3
)
```

## Summary

✅ **Flexible**: Provide any domains at runtime  
✅ **Smart**: Fuzzy matching finds domains automatically  
✅ **Fast**: Fetches from specific sites only  
✅ **Compatible**: Works with all existing filters  
✅ **Non-breaking**: Default behavior unchanged  

**Try it now:**
```python
get_top_news(count=8, domains=['wired', 'verge', 'techradar'])
```
