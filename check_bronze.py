"""Quick summary of Phase 1B Bronze layer"""
from ingestion.minio_client import get_minio_client

client = get_minio_client()
objects = list(client.list_objects('kol-platform', prefix='bronze/raw/', recursive=True))

print("\n📊 PHASE 1B BRONZE LAYER SUMMARY")
print("=" * 70)

sources = {}
for obj in objects:
    source = obj.object_name.split('/')[2]
    if source not in sources:
        sources[source] = {'count': 0, 'size': 0}
    sources[source]['count'] += 1
    sources[source]['size'] += obj.size

for src, info in sorted(sources.items()):
    print(f"   {src}: {info['count']} files, {info['size']/1024/1024:.2f} MB")

total_size = sum(obj.size for obj in objects)
print(f"\n   TOTAL: {len(objects)} files, {total_size/1024/1024:.2f} MB")
print("=" * 70 + "\n")
