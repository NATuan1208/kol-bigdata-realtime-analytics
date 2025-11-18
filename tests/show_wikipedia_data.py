"""
Show Wikipedia scraped data
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from ingestion.sources import wikipedia_backlinko
import json

# Scrape Wikipedia data
print("Scraping Wikipedia for top KOLs...")
records = wikipedia_backlinko.collect(source='wikipedia', limit=10)

print(f'\n✅ Collected {len(records)} records from Wikipedia\n')
print('=' * 70)

# Print first 5 records
for i, rec in enumerate(records[:5], 1):
    print(f'\n{i}. KOL ID: {rec["kol_id"]}')
    print(f'   Platform: {rec["platform"]}')
    print(f'   Source: {rec["source"]}')
    print('   Payload:')
    for key, value in rec["payload"].items():
        print(f'      {key}: {value}')
    print(f'   Ingest Time: {rec["ingest_ts"]}')

print('\n' + '=' * 70)
print(f'\n📊 Summary:')
print(f'   Total records: {len(records)}')
print(f'   Platforms: {", ".join(set(r["platform"] for r in records))}')
print(f'   Sample KOL names: {", ".join([r["kol_id"] for r in records[:5]])}')
