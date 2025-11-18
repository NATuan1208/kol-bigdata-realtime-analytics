# Setup Guide: Mount KOL Catalog vào SME Trino
# ============================================

## Bước 1: Thêm volume mount vào SME Pulse docker-compose.yml

Mở file: `D:\SinhVien\UIT_HocChinhKhoa\HK1 2025 - 2026\SME pulse project\docker-compose.yml`

Tìm service `trino`:
```yaml
  trino:
    build:
      context: ./trino
      dockerfile: Dockerfile
    container_name: sme-trino
    ports:
      - "8081:8080"
    volumes:
      - ./trino/catalog:/etc/trino/catalog  # ← Existing mount
```

**THÊM mount thứ 2** cho KOL catalog:
```yaml
  trino:
    build:
      context: ./trino
      dockerfile: Dockerfile
    container_name: sme-trino
    ports:
      - "8081:8080"
    volumes:
      - ./trino/catalog:/etc/trino/catalog  # SME catalogs
      - ../Bigdata_IE212/DoAn/kol-platform/infra/trino/etc/catalog/kol_lake.properties:/etc/trino/catalog/kol_lake.properties:ro  # ← ADD THIS
```

**Giải thích:**
- Mount 1 file duy nhất `kol_lake.properties` (read-only)
- Đường dẫn tương đối từ SME pulse project → KOL platform
- `:ro` = read-only để bảo vệ file

## Bước 2: Restart SME Trino

```powershell
cd "D:\SinhVien\UIT_HocChinhKhoa\HK1 2025 - 2026\SME pulse project"
docker-compose restart trino
```

Hoặc nếu cần rebuild:
```powershell
docker-compose up -d --force-recreate trino
```

## Bước 3: Verify catalog đã load

```powershell
docker exec sme-trino trino --execute "SHOW CATALOGS;"
```

**Expected output:**
```
"kol_lake"   ← NEW!
"minio"
"sme_lake"
"system"
```

## Bước 4: Tạo schemas trong kol_lake

```powershell
docker exec sme-trino trino --catalog kol_lake --execute "CREATE SCHEMA IF NOT EXISTS kol_lake.kol_bronze WITH (location='s3://kol-platform/bronze/');"

docker exec sme-trino trino --catalog kol_lake --execute "CREATE SCHEMA IF NOT EXISTS kol_lake.kol_silver WITH (location='s3://kol-platform/silver/');"

docker exec sme-trino trino --catalog kol_lake --execute "CREATE SCHEMA IF NOT EXISTS kol_lake.kol_gold WITH (location='s3://kol-platform/gold/');"
```

## Bước 5: Verify schemas

```powershell
docker exec sme-trino trino --catalog kol_lake --execute "SHOW SCHEMAS;"
```

**Expected output:**
```
"information_schema"
"kol_bronze"
"kol_silver"
"kol_gold"
```

## Troubleshooting

**Error: "Failed to create external path"**
→ Kiểm tra MinIO bucket `kol-platform` đã có folders `bronze/`, `silver/`, `gold/`

**Error: "Catalog 'kol_lake' not found"**
→ Kiểm tra mount volume đã đúng và restart Trino

**Error: "Hive Metastore connection failed"**
→ Kiểm tra `sme-hive-metastore` container đang chạy

---

**Sau khi hoàn thành:**
- SME Pulse: Dùng catalog `sme_lake` (không ảnh hưởng)
- KOL Platform: Dùng catalog `kol_lake` (riêng biệt)
- Cả 2 dùng chung 1 Trino instance nhưng data hoàn toàn tách biệt
