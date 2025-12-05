"""
Product Extractor Worker

Flow mới (song song):
- Lắng nghe kol.discovery.raw (username)
- Tự scroll video list của username
- Lấy products từ mỗi video
- Push kol.products.raw

Chạy:
    python -m ingestion.consumers.product_extractor
    
Hoặc với dry-run (không cần Kafka):
    python -m ingestion.consumers.product_extractor --dry-run
"""

import argparse
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from ingestion.consumers.base import BaseConsumer
from ingestion.config import (
    KAFKA_TOPICS,
    CONSUMER_GROUPS,
    MAX_VIDEOS_PER_KOL,
    SCROLL_PAUSE,
)

from selenium.webdriver.common.by import By


class ProductExtractor(BaseConsumer):
    """
    Extract products từ TikTok videos
    
    Input: kol.discovery.raw (username)
    Output: kol.products.raw (product_id, product_title, price, sold_count, ...)
    """
    
    def __init__(self, max_videos: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.max_videos = max_videos
    
    def get_worker_name(self) -> str:
        return "product"
    
    def get_consumer_group(self) -> str:
        return CONSUMER_GROUPS["product_extractor"]
    
    def get_input_topic(self) -> str:
        # Lắng nghe discovery.raw thay vì videos.raw
        return KAFKA_TOPICS["discovery"]
    
    def get_output_topic(self) -> str:
        return KAFKA_TOPICS["products"]
    
    def process_message(self, message: dict) -> List[dict]:
        """
        Nhận username từ discovery → scroll video list → lấy products
        
        Args:
            message: Discovery message với username
            
        Returns:
            List of product dicts
        """
        username = message.get("username")
        if not username:
            return []
        
        print(f"\n🛒 Product extraction for @{username}")
        
        # 1. Scroll video list của username
        video_list = self._scrape_video_list(username)
        print(f"   📹 Found {len(video_list)} videos")
        
        # 2. Lấy products từ mỗi video
        all_products = []
        for i, (video_url, _) in enumerate(video_list):
            if not self.running:
                break
            
            video_id = self._parse_video_id(video_url)
            if not video_id:
                continue
            
            print(f"   [{i+1}/{len(video_list)}] Video {video_id}...", end="")
            
            products = self._scrape_products(video_url, video_id, username)
            all_products.extend(products)
            
            if products:
                print(f" ✅ {len(products)} products")
            else:
                print(f" ⏭️ 0")
            
            time.sleep(0.5)
        
        print(f"   ✅ Total: {len(all_products)} products from {len(video_list)} videos")
        return all_products
    
    def _scrape_video_list(self, username: str) -> List[Tuple[str, Optional[str]]]:
        """Scroll profile và lấy video URLs"""
        url = f"https://www.tiktok.com/@{username}"
        
        if not self._safe_get(url):
            return []
        
        video_data: Dict[str, Optional[str]] = {}
        
        for scroll in range(40):
            if not self.running:
                break
            
            time.sleep(SCROLL_PAUSE)
            
            try:
                anchors = self.driver.find_elements(By.XPATH, "//a[contains(@href,'/video/')]")
                
                for a in anchors:
                    try:
                        href = a.get_attribute("href") or ""
                        if "/video/" not in href:
                            continue
                        
                        if href not in video_data:
                            caption = None
                            for attr in ["title", "aria-label"]:
                                val = a.get_attribute(attr)
                                if val:
                                    caption = val.strip()
                                    break
                            video_data[href] = caption
                    except:
                        continue
                
                if len(video_data) >= self.max_videos:
                    break
                
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            except:
                break
        
        return [(url, caption) for url, caption in list(video_data.items())[:self.max_videos]]
    
    def _scrape_products(self, video_url: str, video_id: str, username: str) -> List[dict]:
        """Extract products từ video page JSON"""
        if not self._safe_get(video_url):
            return []
        
        time.sleep(3)  # Wait for JS to load
        
        products = []
        
        try:
            page_source = self.driver.page_source
            
            # Extract JSON từ page
            pattern = r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>'
            match = re.search(pattern, page_source, re.DOTALL)
            
            if not match:
                return []
            
            json_data = json.loads(match.group(1))
            
            # Navigate to video data
            try:
                item_info = json_data["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"]["itemStruct"]
            except KeyError:
                return []
            
            # Check for product anchors
            anchors = item_info.get("anchors", [])
            if not anchors:
                return []
            
            # Extract products
            for anchor in anchors:
                anchor_type = anchor.get("type")
                
                if anchor_type in [33, 35]:  # Single/Multiple products
                    try:
                        if anchor_type == 35 and "extra" in anchor:
                            # Multiple products
                            extra_data = json.loads(anchor["extra"])
                            for product_data in extra_data:
                                if "id" in product_data:
                                    product_detail = json.loads(product_data.get("extra", "{}"))
                                    product = self._build_product(
                                        username, video_id, video_url,
                                        product_id=product_data["id"],
                                        product_title=product_detail.get("title", ""),
                                        seller_id=str(product_detail.get("seller_id", "")),
                                        price=product_detail.get("price", 0),
                                        currency=product_detail.get("currency", "VND"),
                                        product_url=product_detail.get("seo_url", ""),
                                        keyword=product_data.get("keyword", ""),
                                    )
                                    products.append(product)
                        
                        elif anchor_type == 33:
                            # Single product
                            extra_str = anchor.get("extra", "{}")
                            try:
                                extra_detail = json.loads(extra_str)
                            except:
                                extra_detail = {}
                            
                            product = self._build_product(
                                username, video_id, video_url,
                                product_id=anchor.get("id", ""),
                                product_title=extra_detail.get("title", anchor.get("keyword", "")),
                                seller_id=str(extra_detail.get("seller_id", "")),
                                price=extra_detail.get("price", 0),
                                currency=extra_detail.get("currency", "VND"),
                                product_url=extra_detail.get("seo_url", ""),
                                keyword=anchor.get("keyword", ""),
                            )
                            products.append(product)
                    
                    except Exception as e:
                        self._log_error(f"Product parse error: {e}")
                        continue
            
            # Scrape sold_count for each product
            for product in products:
                if product.get("product_url"):
                    sold_count = self._scrape_sold_count(product["product_url"])
                    if sold_count:
                        product["sold_count"] = sold_count
        
        except Exception as e:
            self._log_error(f"Products extraction error: {e}")
        
        return products
    
    def _build_product(
        self,
        username: str,
        video_id: str,
        video_url: str,
        **kwargs
    ) -> dict:
        """Build product dict - chỉ product info, video stats sẽ join sau từ videos table"""
        product = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "product",
            "platform": "tiktok",
            "username": username,
            "video_id": video_id,  # FK để join với videos table
            "video_url": video_url,
            **kwargs
        }
        
        return product
    
    def _scrape_sold_count(self, product_url: str) -> Optional[int]:
        """Scrape sold_count từ product page"""
        if not product_url:
            return None
        
        try:
            self.driver.get(product_url)
            time.sleep(3)
            
            page_source = self.driver.page_source
            
            # Find sold count patterns
            sold_patterns = [
                r'([\d,.]+[KkMm]?)\s*(?:đã bán|sold)',
                r'"sold_count"[:\s]*["\s]*(\d+)',
            ]
            
            for pattern in sold_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    for m in matches:
                        result = self._parse_sold_count(m)
                        if result:
                            return result
        except:
            pass
        
        return None
    
    def _parse_sold_count(self, sold_text: str) -> Optional[int]:
        """Convert '188.5K' → 188500"""
        if not sold_text:
            return None
        
        text = sold_text.strip().upper().replace(',', '')
        multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}
        
        for suffix, mult in multipliers.items():
            if suffix in text:
                try:
                    num = float(text.replace(suffix, ''))
                    return int(num * mult)
                except:
                    pass
        
        try:
            return int(float(text.replace('.', '')))
        except:
            return None


    def _parse_video_id(self, url: str) -> Optional[str]:
        """Extract video ID từ URL"""
        m = re.search(r"/video/(\d+)", url)
        return m.group(1) if m else None


def main():
    parser = argparse.ArgumentParser(description="Product Extractor Worker")
    parser.add_argument("--dry-run", action="store_true", help="Run without Kafka")
    parser.add_argument("--no-selenium", action="store_true", help="Disable Selenium")
    parser.add_argument("--max-videos", type=int, default=20)
    args = parser.parse_args()
    
    consumer = ProductExtractor(
        use_selenium=not args.no_selenium,
        dry_run=args.dry_run,
        max_videos=args.max_videos,
    )
    consumer.run()


if __name__ == "__main__":
    main()
