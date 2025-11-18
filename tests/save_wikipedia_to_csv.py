"""
Save Wikipedia data to CSV for inspection
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from ingestion.sources import wikipedia_backlinko
import pandas as pd
from pathlib import Path

# Scrape Wikipedia data
print("🔍 Scraping Wikipedia for top KOLs...")
records = wikipedia_backlinko.collect(source='wikipedia', limit=50)

print(f'✅ Collected {len(records)} records from Wikipedia\n')

if not records:
    print("❌ No records collected!")
    exit(1)

# Convert to DataFrame for easy viewing
rows = []
for rec in records:
    row = {
        'kol_id': rec['kol_id'],
        'platform': rec['platform'],
        'source': rec['source'],
        'ingest_ts': rec['ingest_ts']
    }
    # Add all payload fields
    for key, value in rec['payload'].items():
        row[f'payload_{key}'] = value
    rows.append(row)

df = pd.DataFrame(rows)

# Save to CSV
output_path = Path('data/wikipedia/scraped_kols.csv')
output_path.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(output_path, index=False, encoding='utf-8')

print(f'💾 Saved to: {output_path}')
print(f'\n📊 Preview (first 10 rows):\n')
print(df.head(10).to_string())

print(f'\n✅ Total: {len(df)} KOL records')
print(f'📁 File location: {output_path.absolute()}')
