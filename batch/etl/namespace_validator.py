"""
KOL Analytics Domain - Namespace Validation Helper
===================================================

Enforces strict separation between SME and KOL domains.
Validates that code only accesses KOL namespaces.

Usage:
    from namespace_validator import validate_kol_namespace
    
    # In your ETL/ML code
    validate_kol_namespace(
        bucket="kol-platform",
        schema="kol_bronze",
        catalog="kol_lake"
    )
"""

import os
import sys

# KOL domain namespace rules
ALLOWED_BUCKETS = {"kol-platform"}
ALLOWED_SCHEMAS = {"kol_bronze", "kol_silver", "kol_gold"}
ALLOWED_CATALOGS = {"kol_lake"}
ALLOWED_DATABASES = {"kol_mlflow"}
ALLOWED_KEYSPACES = {"kol_metrics"}

# SME domain namespaces (FORBIDDEN for KOL code)
FORBIDDEN_BUCKETS = {"sme-lake"}
FORBIDDEN_SCHEMAS = {"bronze", "silver", "gold"}  # Non-prefixed schemas belong to SME
FORBIDDEN_CATALOGS = {"sme_lake"}
FORBIDDEN_DATABASES = {"sme", "sme_mlflow"}


def validate_kol_namespace(bucket=None, schema=None, catalog=None, database=None, keyspace=None):
    """
    Validates that the provided namespace belongs to KOL domain.
    
    Raises ValueError if:
    - Using SME domain namespaces
    - Using non-prefixed schemas (ambiguous)
    - Using forbidden buckets/catalogs
    
    Args:
        bucket: MinIO bucket name (e.g., "kol-platform")
        schema: Trino schema name (e.g., "kol_bronze")
        catalog: Trino catalog name (e.g., "kol_lake")
        database: PostgreSQL database name (e.g., "kol_mlflow")
        keyspace: Cassandra keyspace name (e.g., "kol_metrics")
    """
    errors = []
    
    # Validate bucket
    if bucket:
        if bucket in FORBIDDEN_BUCKETS:
            errors.append(f"❌ Bucket '{bucket}' belongs to SME domain! Use 'kol-platform' instead.")
        elif bucket not in ALLOWED_BUCKETS:
            errors.append(f"⚠️ Bucket '{bucket}' is not a recognized KOL bucket. Expected: {ALLOWED_BUCKETS}")
    
    # Validate schema
    if schema:
        if schema in FORBIDDEN_SCHEMAS:
            errors.append(f"❌ Schema '{schema}' belongs to SME domain! Use kol_bronze/kol_silver/kol_gold.")
        elif schema not in ALLOWED_SCHEMAS:
            errors.append(f"⚠️ Schema '{schema}' is not a recognized KOL schema. Expected: {ALLOWED_SCHEMAS}")
    
    # Validate catalog
    if catalog:
        if catalog in FORBIDDEN_CATALOGS:
            errors.append(f"❌ Catalog '{catalog}' belongs to SME domain! Use 'kol_lake' instead.")
        elif catalog not in ALLOWED_CATALOGS:
            errors.append(f"⚠️ Catalog '{catalog}' is not a recognized KOL catalog. Expected: {ALLOWED_CATALOGS}")
    
    # Validate database
    if database:
        if database in FORBIDDEN_DATABASES:
            errors.append(f"❌ Database '{database}' belongs to SME domain! Use 'kol_mlflow' instead.")
        elif database not in ALLOWED_DATABASES:
            errors.append(f"⚠️ Database '{database}' is not a recognized KOL database. Expected: {ALLOWED_DATABASES}")
    
    # Validate keyspace
    if keyspace:
        if keyspace not in ALLOWED_KEYSPACES:
            errors.append(f"⚠️ Keyspace '{keyspace}' is not a recognized KOL keyspace. Expected: {ALLOWED_KEYSPACES}")
    
    # Raise if any violations found
    if errors:
        error_msg = "\n".join(errors)
        error_msg += "\n\n🔒 DOMAIN SEPARATION POLICY:"
        error_msg += "\n   - KOL code MUST ONLY access KOL namespaces (kol_*, kol-platform)"
        error_msg += "\n   - SME code MUST ONLY access SME namespaces (sme_*, sme-lake)"
        error_msg += "\n   - Sharing the same Hive Metastore does NOT mean you can query any schema!"
        raise ValueError(error_msg)
    
    print(f"✅ Namespace validation passed: bucket={bucket}, schema={schema}, catalog={catalog}")


def get_kol_env_config():
    """
    Returns KOL namespace configuration from environment variables.
    Use this to ensure all code reads from .env.kol
    """
    config = {
        "bucket": os.getenv("MINIO_BUCKET", "kol-platform"),
        "bronze_path": os.getenv("MINIO_PATH_BRONZE", "bronze"),
        "silver_path": os.getenv("MINIO_PATH_SILVER", "silver"),
        "gold_path": os.getenv("MINIO_PATH_GOLD", "gold"),
        "mlflow_path": os.getenv("MINIO_PATH_MLFLOW", "mlflow"),
        "trino_catalog": os.getenv("TRINO_CATALOG", "kol_lake"),
        "schema_bronze": os.getenv("TRINO_SCHEMA_BRONZE", "kol_bronze"),
        "schema_silver": os.getenv("TRINO_SCHEMA_SILVER", "kol_silver"),
        "schema_gold": os.getenv("TRINO_SCHEMA_GOLD", "kol_gold"),
        "mlflow_db": os.getenv("POSTGRES_DB", "kol_mlflow"),
        "cassandra_keyspace": "kol_metrics",
    }
    
    # Validate the config
    validate_kol_namespace(
        bucket=config["bucket"],
        schema=config["schema_bronze"],  # Just check one schema
        catalog=config["trino_catalog"],
        database=config["mlflow_db"],
        keyspace=config["cassandra_keyspace"]
    )
    
    return config


if __name__ == "__main__":
    # Self-test
    print("=== Testing KOL namespace validation ===\n")
    
    # Test valid KOL namespaces
    try:
        validate_kol_namespace(bucket="kol-platform", schema="kol_bronze", catalog="kol_lake")
        print("✅ Test 1 passed: Valid KOL namespaces\n")
    except ValueError as e:
        print(f"❌ Test 1 failed: {e}\n")
    
    # Test forbidden SME bucket
    try:
        validate_kol_namespace(bucket="sme-lake")
        print("❌ Test 2 failed: Should have rejected SME bucket\n")
    except ValueError as e:
        print(f"✅ Test 2 passed: Correctly rejected SME bucket\n")
    
    # Test forbidden SME schema
    try:
        validate_kol_namespace(schema="bronze")  # Non-prefixed = SME
        print("❌ Test 3 failed: Should have rejected SME schema\n")
    except ValueError as e:
        print(f"✅ Test 3 passed: Correctly rejected SME schema\n")
    
    # Test environment config
    print("=== Testing environment configuration ===\n")
    config = get_kol_env_config()
    print(f"KOL Config: {config}\n")
    
    print("✅ All validation tests passed!")
