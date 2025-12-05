"""
KOL Platform - Ingestion Consumers

Các Kafka consumers chạy song song để extract data từ videos:
- CommentExtractor: Extract comments từ videos
- ProductExtractor: Extract products từ videos

Mỗi consumer sử dụng Chrome profile riêng để tránh conflict.
"""

from ingestion.consumers.base import BaseConsumer
from ingestion.consumers.comment_extractor import CommentExtractor
from ingestion.consumers.product_extractor import ProductExtractor

__all__ = [
    "BaseConsumer",
    "CommentExtractor", 
    "ProductExtractor",
]
