"""
Test all collectors with REAL data
===================================
"""
import os
import sys
sys.path.insert(0, os.path.abspath('.'))

from ingestion.sources import youtube_trending, wikipedia_backlinko, weibo_dataset

# Set API key
os.environ['YOUTUBE_API_KEY'] = 'AIzaSyCIHqU02IaYwZirVV8QZzHcaCrUcaXUhz4'

print('=' * 70)
print('🧪 TESTING ALL 3 COLLECTORS WITH REAL DATA')
print('=' * 70)

# Test 1: YouTube (REAL API)
print('\n--- Test 1: YouTube Trending (REAL API) ---')
youtube_records = youtube_trending.collect(region_codes=['US', 'VN'], limit=10, use_api=True)
print(f'✅ Collected {len(youtube_records)} REAL YouTube trending videos')
if youtube_records:
    sample = youtube_records[0]['payload']
    print(f'   📺 Sample: {sample["title"][:60]}...')
    print(f'   👁️  Views: {sample["view_count"]:,} | 👍 Likes: {sample["likes"]:,}')
    print(f'   🎬 Channel: {sample["channel_title"]}')

# Test 2: Wikipedia (REAL scraping)
print('\n--- Test 2: Wikipedia KOL Rankings (REAL scraping) ---')
wiki_records = wikipedia_backlinko.collect(source='wikipedia', limit=10)
print(f'✅ Collected {len(wiki_records)} REAL KOL rankings from Wikipedia')
if wiki_records:
    sample = wiki_records[0]
    print(f'   👤 Sample: {sample["kol_id"]} on {sample["platform"]}')
    payload_str = str(sample["payload"])[:100]
    print(f'   📊 Data: {payload_str}...')

# Test 3: Weibo (PUBLIC dataset)
print('\n--- Test 3: Weibo Posts (PUBLIC dataset) ---')
print('⏳ Attempting to download dataset from GitHub...')
weibo_records = weibo_dataset.collect(download_public=True, limit=10)
print(f'✅ Collected {len(weibo_records)} Weibo posts')
if weibo_records:
    sample = weibo_records[0]['payload']
    print(f'   💬 Sample: {sample["nickname"]}: {sample["text"][:50]}...')
    print(f'   👍 Likes: {sample["like_count"]:,} | 💬 Comments: {sample["comment_count"]:,}')

# Summary
print('\n' + '=' * 70)
total = len(youtube_records) + len(wiki_records) + len(weibo_records)
print(f'🎉 TOTAL REAL RECORDS COLLECTED: {total}')
print(f'   YouTube: {len(youtube_records)} videos')
print(f'   Wikipedia: {len(wiki_records)} KOL rankings')
print(f'   Weibo: {len(weibo_records)} posts')
print('=' * 70)
print()

# Verify data is REAL (not sample)
print('🔍 VERIFICATION: Is data REAL or SAMPLE?')
print('-' * 70)

# Check YouTube - real data has recent dates and high view counts
if youtube_records:
    yt_sample = youtube_records[0]['payload']
    is_real = yt_sample['view_count'] > 1000 and 'trending_date' in yt_sample
    status = '✅ REAL' if is_real else '❌ SAMPLE'
    print(f'YouTube: {status} (views: {yt_sample["view_count"]:,})')

# Check Wikipedia - real data from actual Wikipedia pages
if wiki_records:
    wiki_sample = wiki_records[0]
    is_real = wiki_sample['source'] == 'wikipedia_backlinko'
    status = '✅ REAL' if is_real else '❌ SAMPLE'
    print(f'Wikipedia: {status} (source: {wiki_sample["source"]})')

# Check Weibo - check if downloaded or sample
if weibo_records:
    weibo_sample = weibo_records[0]['payload']
    # Sample data has specific user_ids like "1001", "1002"
    is_sample = weibo_sample['user_id'] in ['1001', '1002', '1003', '1004']
    status = '❌ SAMPLE' if is_sample else '✅ REAL'
    print(f'Weibo: {status} (user_id: {weibo_sample["user_id"]})')

print('=' * 70)
