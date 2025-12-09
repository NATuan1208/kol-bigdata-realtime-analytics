#!/bin/bash
# Entrypoint for YouTube KOL Scraper Container (API-based)
# Runs multiple workers using supervisord (NO Selenium/Xvfb needed!)

set -e

echo "🎬 Starting YouTube KOL Platform (API-based)..."
echo "================================================"

# Check API key
if [ -z "$YOUTUBE_API_KEY" ]; then
    echo "❌ ERROR: YOUTUBE_API_KEY not set!"
    echo "   Please set it in docker-compose.yml or .env"
    exit 1
fi

echo "✅ YouTube API Key: ${YOUTUBE_API_KEY:0:20}..."
echo "✅ Kafka: $KAFKA_BOOTSTRAP_SERVERS"
echo "✅ Region: ${REGION:-VN}"
echo ""

# Write supervisord config
cat > /tmp/supervisord.conf <<EOF
[supervisord]
nodaemon=true
logfile=/dev/stdout
logfile_maxbytes=0
loglevel=info

[program:youtube_discovery]
command=python -m ingestion.sources.youtube_discovery_api daemon --max-channels %(ENV_MAX_CHANNELS)s --interval %(ENV_DISCOVERY_INTERVAL)s --region %(ENV_REGION)s --kafka-broker %(ENV_KAFKA_BOOTSTRAP_SERVERS)s --api-key %(ENV_YOUTUBE_API_KEY)s
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=YOUTUBE_API_KEY="%(ENV_YOUTUBE_API_KEY)s"

[program:youtube_stats_worker]
command=python -m ingestion.consumers.youtube_stats_worker --max-videos %(ENV_MAX_VIDEOS)s --start-delay 240 --kafka-broker %(ENV_KAFKA_BOOTSTRAP_SERVERS)s
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=YOUTUBE_API_KEY="%(ENV_YOUTUBE_API_KEY)s",REDIS_HOST="kol-redis",REDIS_PORT="6379"

[program:youtube_comments_worker]
command=python -m ingestion.consumers.youtube_comments_worker --max-comments 100 --start-delay 240 --delay-between-videos %(ENV_COMMENT_DELAY)s --kafka-broker %(ENV_KAFKA_BOOTSTRAP_SERVERS)s
directory=/app
autostart=true
autorestart=%(ENV_ENABLE_COMMENTS)s
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=YOUTUBE_API_KEY="%(ENV_YOUTUBE_API_KEY)s"

[program:metrics_refresh]
command=python -m ingestion.sources.metrics_refresh --interval %(ENV_REFRESH_INTERVAL)s --kafka-broker %(ENV_KAFKA_BOOTSTRAP_SERVERS)s --redis-host kol-redis --redis-port 6379
directory=/app
autostart=%(ENV_ENABLE_REFRESH)s
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
EOF

echo "🚀 Starting supervisord with 4 workers..."
echo "   1. YouTube Discovery"
echo "   2. YouTube Stats Worker"
echo "   3. YouTube Comments Worker"
echo "   4. Metrics Refresh"
echo ""

exec supervisord -c /tmp/supervisord.conf
