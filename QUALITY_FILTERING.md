# Quality Filtering System - NewsNexus

## Overview

The NewsNexus framework now includes an **intelligent quality filtering system** that prioritizes informative, substantive news over vague headlines and clickbait. This is especially powerful for AI and tech news, ensuring you get meaningful content rather than speculative or low-quality articles.

## Problem Solved

**Before**: You might get articles like:
- "Wall Street optimistic about AI-driven productivity gains in 2026" (vague sentiment)
- "Company eyes expansion into new markets" (speculative, uninformative)
- "You won't believe what happened next" (clickbait)

**After**: You get high-quality, informative articles with:
- Concrete information and data
- Specific details about AI/tech developments
- Substantive content from credible sources
- Recent, relevant news

## How It Works

### Quality Scoring (0-100 points)

Each article is scored based on multiple factors:

#### 1. **Content Informativeness** (0-40 points)
- Longer, more detailed summaries score higher
- Bonus for concrete data: percentages, dollar amounts, specific numbers
- Example: "OpenAI raises $6.6 billion at $157 billion valuation" gets high marks

#### 2. **Source Credibility** (0-20 points)
- Based on domain priority in `sites.json`
- Priority 1-3 sites (NDTV, Indian Express, etc.) = 20 points
- Priority 4-6 sites = 15 points
- Priority 7-9 sites = 10 points
- Priority 10-12 sites = 5 points

#### 3. **Keyword Richness for AI/Tech** (0-30 points)
- **AI Keywords** (highest boost): artificial intelligence, machine learning, GPT, LLM, ChatGPT, Gemini, Claude, neural network, transformer, etc.
- **Tech Keywords** (good boost): innovation, breakthrough, algorithm, quantum, cybersecurity, open source, etc.
- **Business Keywords** (moderate boost): funding, acquisition, IPO, launch, partnership, etc.

Articles with 3+ AI keywords get the maximum 30 points!

#### 4. **Recency Boost** (0-10 points)
- Less than 6 hours old: 10 points
- Less than 24 hours: 7 points
- Less than 48 hours: 5 points
- Less than 72 hours: 3 points

#### 5. **Quality Penalties** (-15 points)
Articles are penalized for low-quality patterns:
- Vague sentiment: "optimistic about", "pessimistic about"
- Speculative language: "may be", "could be", "set to"
- Unconfirmed: "reportedly", "rumors"
- Clickbait: "you won't believe", "shocking", "amazing"
- Listicles: "10 things you need to know"

### Deep Search Mode

If the system can't find enough high-quality articles from the initial 12 priority sites, it **automatically expands** the search:

1. **Phase 1**: Fetch from top 12 priority sites
2. **Quality Check**: Score and filter articles
3. **Phase 2** (if needed): Fetch from 8 additional sites (total 20)
4. **Result**: Guaranteed to find quality content if it exists

## Usage

### Default Behavior (Recommended)

```python
# Quality filtering is ON by default with balanced threshold
get_top_news(count=8)
```

This will:
- Filter out vague/clickbait content
- Prioritize AI/tech news
- Use deep search if needed
- Return 8 high-quality articles

### Custom Quality Threshold

```python
# Stricter filtering - only premium content
get_top_news(count=8, min_quality_score=45.0)

# More lenient - include more articles
get_top_news(count=8, min_quality_score=30.0)

# Very strict - only the best
get_top_news(count=8, min_quality_score=50.0)
```

**Recommended thresholds**:
- **30-35**: Balanced, filters obvious low-quality content
- **35-40**: Good quality, filters vague headlines (default: 35)
- **40-50**: High quality, only substantive articles
- **50+**: Premium only, very strict

### Disable Quality Filtering

```python
# Get all articles without quality filtering
get_top_news(count=8, enable_quality_filter=False)
```

### Topic-Specific Quality Filtering

```python
# Get high-quality AI news
get_top_news(count=8, topic="ai", min_quality_score=40.0)

# Get quality tech startup news
get_top_news(count=8, topic="startup", min_quality_score=35.0)
```

## Response Format

With quality filtering enabled, each article includes a `quality_score`:

```json
{
  "articles": [
    {
      "heading": "OpenAI launches GPT-5 with breakthrough reasoning capabilities",
      "summary": "OpenAI announced GPT-5 today with 10x improved reasoning...",
      "date": "2025-12-26T18:00:00Z",
      "source_link": "https://...",
      "quality_score": 85.5
    }
  ],
  "total": 8,
  "durationMs": 3245.67,
  "qualityFilterEnabled": true,
  "minQualityScore": 35.0,
  "filteredOut": 47
}
```

**Metadata**:
- `qualityFilterEnabled`: Whether quality filtering was used
- `minQualityScore`: Threshold that was applied
- `filteredOut`: Number of articles filtered out for low quality
- `quality_score`: Individual article score (0-100)

## Examples

### Example 1: Default Quality Filtering

**Input**:
```python
get_top_news(count=8)
```

**What happens**:
1. Fetches from top 12 priority sites
2. Scores all articles
3. Filters out articles with score < 35
4. If < 8 quality articles found, fetches from 8 more sites
5. Returns top 8 by quality score

**Result**: 8 high-quality, informative articles

### Example 2: Strict AI News

**Input**:
```python
get_top_news(count=10, topic="ai", min_quality_score=45.0)
```

**What happens**:
1. Fetches AI-related articles
2. Applies strict quality threshold (45)
3. Prioritizes articles with AI keywords
4. Deep search if needed
5. Returns top 10 premium AI articles

**Result**: Only the most informative AI news

### Example 3: Comparison

**Without quality filter**:
```
1. "Wall Street optimistic about AI-driven productivity gains in 2026"
2. "Tech company eyes expansion into Asian markets"
3. "Startup may raise funding next quarter"
```

**With quality filter (min_score=35)**:
```
1. "OpenAI raises $6.6B at $157B valuation, announces GPT-5 development"
2. "Google DeepMind's AlphaFold 3 predicts protein structures with 95% accuracy"
3. "Microsoft launches Copilot Pro with advanced AI coding capabilities"
```

## Configuration

### Environment Variables

```bash
# Disable quality filtering globally (not recommended)
export NEWSNEXUS_QUALITY_FILTER=false

# Set default minimum quality score
export NEWSNEXUS_MIN_QUALITY=40.0
```

### Customizing Quality Indicators

Edit `main.py` to customize keywords:

```python
QUALITY_INDICATORS = {
    'ai': [
        'artificial intelligence', 'machine learning', 'gpt', 'llm',
        # Add your custom AI keywords
    ],
    'tech': [
        'innovation', 'breakthrough', 'algorithm',
        # Add your custom tech keywords
    ]
}
```

### Customizing Low-Quality Patterns

```python
LOW_QUALITY_PATTERNS = [
    r'\b(optimistic|pessimistic)\s+about\b',
    r'\beyes\s+(on|for)\b',
    # Add your custom patterns to filter
]
```

## Performance

- **Phase 1**: ~3-5 seconds (12 sites in parallel)
- **Phase 2** (if triggered): +2-3 seconds (8 more sites)
- **Total**: Usually 3-8 seconds for high-quality results

The deep search mode ensures you get quality content without sacrificing too much speed.

## Best Practices

1. **Use default settings** for balanced results (min_score=35)
2. **Increase threshold** for premium content (min_score=40-50)
3. **Decrease threshold** if you need more articles (min_score=30)
4. **Combine with topic filter** for focused quality news
5. **Monitor `filteredOut`** to see how many low-quality articles were removed

## Troubleshooting

**Q: I'm getting fewer than requested articles**
- A: Lower the `min_quality_score` threshold
- Or: Increase `lastNDays` to search more days
- Or: Disable quality filtering temporarily

**Q: Articles still seem low quality**
- A: Increase `min_quality_score` to 40-50
- Or: Add custom patterns to `LOW_QUALITY_PATTERNS`

**Q: Too slow**
- A: Reduce `count` parameter
- Or: Use `fast_mode=True` for single domains
- Or: Disable deep search by setting a lower count

## Summary

The quality filtering system ensures you get **informative, substantive news** rather than vague headlines. It's especially powerful for AI and tech news, automatically prioritizing breakthrough announcements, funding news, and technical developments over speculative content.

**Key Benefits**:
- ✅ Filters out vague, clickbait content
- ✅ Prioritizes AI/tech news with rich keywords
- ✅ Automatic deep search for quality content
- ✅ Configurable quality thresholds
- ✅ Fast parallel fetching
- ✅ Transparent quality scores
