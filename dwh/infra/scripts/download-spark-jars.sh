#!/bin/bash
# Download required JARs for Spark to access S3 and Iceberg

SPARK_VERSION=3.5
SCALA_VERSION=2.12
HADOOP_VERSION=3.3.4
ICEBERG_VERSION=1.4.3
AWS_SDK_VERSION=2.20.18

JAR_DIR="/opt/spark/jars"

echo "📦 Downloading Hadoop AWS JARs..."
curl -L -o ${JAR_DIR}/hadoop-aws-${HADOOP_VERSION}.jar \
  https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_VERSION}/hadoop-aws-${HADOOP_VERSION}.jar

curl -L -o ${JAR_DIR}/aws-java-sdk-bundle-1.12.262.jar \
  https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar

echo "📦 Downloading Iceberg Spark JARs..."
curl -L -o ${JAR_DIR}/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}-${ICEBERG_VERSION}.jar \
  https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}/${ICEBERG_VERSION}/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}-${ICEBERG_VERSION}.jar

echo "✅ JAR download complete!"
ls -lh ${JAR_DIR}/*.jar | grep -E "(hadoop-aws|aws-java|iceberg)"
