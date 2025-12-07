import json

sites = json.load(open('sites.json'))

# Get priority sites 1-12
priority_sites = [
    s for s in sites 
    if s.get('priority') is not None 
    and isinstance(s.get('priority'), int) 
    and 1 <= s.get('priority') <= 12
]

priority_sites.sort(key=lambda x: x['priority'])

print('Official RSS Feed Status for 12 Priority Sites:')
print('=' * 80)

sites_with_rss = []
sites_without_rss = []

for s in priority_sites:
    official_rss = next(
        (src for src in s.get('sources', []) if src.get('type') == 'official_rss'),
        None
    )
    
    has_url = official_rss and official_rss.get('url') and official_rss.get('url').strip()
    
    status = '✓ YES' if has_url else '✗ NO'
    url = official_rss.get('url', 'NONE') if official_rss else 'NONE'
    
    print(f"{s['priority']:2d}. {s['name']:35s} {status:6s}  {url}")
    
    if has_url:
        sites_with_rss.append(s['name'])
    else:
        sites_without_rss.append(s['name'])

print('=' * 80)
print(f"\nSummary:")
print(f"Sites WITH official RSS: {len(sites_with_rss)}")
print(f"Sites WITHOUT official RSS: {len(sites_without_rss)}")

if sites_without_rss:
    print(f"\nSites missing official RSS feeds:")
    for name in sites_without_rss:
        print(f"  - {name}")
