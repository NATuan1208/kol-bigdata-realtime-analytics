#!/bin/bash
# ============================================================================
# Cassandra Initialization Script
# ============================================================================
# Wait for Cassandra to be ready, then create keyspace and tables
# ============================================================================

set -e

echo "Waiting for Cassandra to be ready..."
until cqlsh -e "describe cluster" > /dev/null 2>&1; do
  echo "Cassandra is unavailable - sleeping"
  sleep 5
done

echo "Cassandra is up - executing schema initialization"
cqlsh -f /docker-entrypoint-initdb.d/init-cassandra.cql

echo "Cassandra initialization completed"
