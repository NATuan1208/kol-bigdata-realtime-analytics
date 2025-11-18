"""
Spark Structured Streaming Job - Real-time Windowed Metrics
============================================================

DOMAIN SEPARATION: This job is part of KOL Analytics domain.
- Reads from KOL Kafka topics (events.social.raw, events.web.raw, events.tx.raw)
- Writes to KOL Cassandra keyspace (kol_metrics)
- Does NOT touch SME Pulse data or tables

This job processes events from Kafka in real-time using Spark Structured Streaming:
- Reads from Redpanda/Kafka topics (events.social.raw, events.web.raw, events.tx.raw)
- Performs windowed aggregations (5-15 minute tumbling windows)
- Calculates KPIs: CTR, CVR, engagement rate, follower velocity
- Writes to Cassandra for real-time metrics (kol_metrics keyspace)
- Writes to Redis for feature cache (kol: prefix)

Usage:
    spark-submit \
        --master spark://spark-master:7077 \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,\
                   com.datastax.spark:spark-cassandra-connector_2.12:3.4.1 \
        features_stream.py

Or from container:
    docker exec kol-spark-streaming spark-submit \
        --master spark://spark-master:7077 \
        /opt/spark-jobs/features_stream.py
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, window, sum as _sum, count, avg,
    to_timestamp, current_timestamp
)
from pyspark.sql.types import StructType, StructField, StringType, LongType, DoubleType, TimestampType

# Event schema from Kafka
EVENT_SCHEMA = StructType([
    StructField("kol_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("event_time", TimestampType(), False),
    StructField("campaign_id", StringType(), True),
    StructField("impressions", LongType(), True),
    StructField("clicks", LongType(), True),
    StructField("conversions", LongType(), True),
    StructField("revenue", DoubleType(), True),
])


def create_spark_session():
    """Create Spark session with Kafka and Cassandra connectors"""
    return SparkSession.builder \
        .appName("KOL-RealTime-Metrics") \
        .config("spark.sql.streaming.checkpointLocation", "/opt/spark/checkpoints/metrics") \
        .config("spark.cassandra.connection.host", "cassandra") \
        .config("spark.cassandra.connection.port", "9042") \
        .getOrCreate()


def read_kafka_stream(spark, topic="events.social.raw"):
    """Read streaming data from Kafka"""
    return spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "redpanda:9092") \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .load()


def parse_events(df):
    """Parse JSON events from Kafka"""
    return df.select(
        from_json(col("value").cast("string"), EVENT_SCHEMA).alias("event")
    ).select("event.*")


def calculate_windowed_metrics(events_df):
    """
    Calculate windowed metrics (5-minute tumbling windows)
    
    Metrics:
    - total_impressions
    - total_clicks
    - total_conversions
    - total_revenue
    - ctr (Click-Through Rate)
    - cvr (Conversion Rate)
    """
    windowed = events_df \
        .withWatermark("event_time", "10 minutes") \
        .groupBy(
            col("kol_id"),
            col("campaign_id"),
            window(col("event_time"), "5 minutes")
        ) \
        .agg(
            _sum("impressions").alias("total_impressions"),
            _sum("clicks").alias("total_clicks"),
            _sum("conversions").alias("total_conversions"),
            _sum("revenue").alias("total_revenue"),
            count("*").alias("event_count")
        ) \
        .select(
            col("kol_id"),
            col("campaign_id"),
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("total_impressions"),
            col("total_clicks"),
            col("total_conversions"),
            col("total_revenue"),
            col("event_count"),
            # Calculate rates
            (col("total_clicks") / col("total_impressions")).alias("ctr"),
            (col("total_conversions") / col("total_clicks")).alias("cvr"),
            current_timestamp().alias("processed_at")
        )
    
    return windowed


def write_to_cassandra(df, table="kol_realtime_metrics"):
    """Write streaming results to Cassandra"""
    return df.writeStream \
        .format("org.apache.spark.sql.cassandra") \
        .option("keyspace", "kol_metrics") \
        .option("table", table) \
        .outputMode("update") \
        .option("checkpointLocation", f"/opt/spark/checkpoints/{table}") \
        .start()


def write_to_console(df, output_mode="update"):
    """Write to console for debugging"""
    return df.writeStream \
        .format("console") \
        .outputMode(output_mode) \
        .option("truncate", False) \
        .start()


def main():
    """Main streaming job"""
    print("Starting KOL Real-time Metrics Streaming Job...")
    
    # Create Spark session
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    # Read from Kafka
    print("Reading from Kafka topic: events.social.raw")
    raw_stream = read_kafka_stream(spark, topic="events.social.raw")
    
    # Parse events
    events = parse_events(raw_stream)
    
    # Calculate windowed metrics
    print("Calculating 5-minute windowed metrics...")
    metrics = calculate_windowed_metrics(events)
    
    # Write to Cassandra (production)
    cassandra_query = write_to_cassandra(metrics)
    
    # Write to console (debugging)
    console_query = write_to_console(metrics)
    
    print("Streaming job started successfully!")
    print("- Writing metrics to Cassandra: kol_metrics.kol_realtime_metrics")
    print("- Writing to console for debugging")
    print("\nPress Ctrl+C to stop...")
    
    # Wait for termination
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()

