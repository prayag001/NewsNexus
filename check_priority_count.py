import json

sites = json.load(open('sites.json', encoding='utf-8'))

priority_sites = [
    s for s in sites 
    if s.get('priority') is not None 
    and isinstance(s.get('priority'), int)
]

priority_sites.sort(key=lambda x: x['priority'])

print(f'Total priority sites: {len(priority_sites)}\n')
print('Current Priority Sites:')
print('=' * 60)
for s in priority_sites:
    print(f"{s['priority']:2d}. {s['name']:40s} ({s['domain']})")
