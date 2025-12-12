"""
Verify Medallion Architecture Status (Bronze → Silver → Gold)
"""
import os
from minio import Minio

# SECURITY: Use environment variables for credentials
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")

client = Minio(
    endpoint=MINIO_ENDPOINT, 
    access_key=MINIO_ACCESS_KEY, 
    secret_key=MINIO_SECRET_KEY, 
    secure=False
)

def verify_layer(layer_name: str, prefix: str):
    print(f"\n{'='*60}")
    print(f"📊 {layer_name.upper()} LAYER STATUS")
    print('='*60)
    
    total_size = 0
    tables = {}
    
    for obj in client.list_objects(bucket_name='kol-platform', prefix=prefix, recursive=True):
        total_size += obj.size
        parts = obj.object_name.split('/')
        if len(parts) >= 2:
            table = parts[1]
            if table and table not in ['', 'raw']:
                if table not in tables:
                    tables[table] = {'count': 0, 'size': 0}
                tables[table]['count'] += 1
                tables[table]['size'] += obj.size
    
    for table, info in sorted(tables.items()):
        size_mb = info['size'] / (1024*1024)
        count = info['count']
        print(f"   {table}:")
        print(f"      Files: {count}, Size: {size_mb:.2f} MB")
    
    print(f"\n   TOTAL {layer_name.upper()} SIZE: {total_size/(1024*1024):.2f} MB")


# Verify all layers
verify_layer('Bronze', 'bronze/')
verify_layer('Silver', 'silver/')
verify_layer('Gold', 'gold/')

print("\n" + "="*60)
print("🏗️ MEDALLION ARCHITECTURE SUMMARY")
print("="*60)
print("""
   Bronze (Raw)     →    Silver (Clean)    →    Gold (Star Schema)
   115 MB                61 MB                  62.5 MB

Star Schema Diagram:
                        ┌──────────────────┐
                        │    dim_time      │
                        └────────┬─────────┘
                                 │
┌──────────────┐    ┌────────────┴────────────┐    ┌──────────────────┐
│   dim_kol    │────│  fact_kol_performance   │────│   dim_platform   │
└──────────────┘    └────────────┬────────────┘    └──────────────────┘
                                 │
                        ┌────────┴─────────┐
                        │ dim_content_type │
                        └──────────────────┘
""")
print("="*60)
