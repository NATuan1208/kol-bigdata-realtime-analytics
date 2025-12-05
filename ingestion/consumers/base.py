"""
Base Consumer - Abstract class cho Kafka consumers

Cung cấp:
- Kafka consumer setup với graceful shutdown
- Selenium driver management (1 driver per consumer)
- Message processing loop
- Error handling và logging
"""

import json
import signal
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any, Dict

# Add project root to path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.config import (
    KAFKA_BROKER,
    KAFKA_TOPICS,
    CONSUMER_GROUPS,
    CHROME_DRIVER_PATH,
    CHROME_PROFILES,
    LOG_DIR,
    SCROLL_PAUSE,
    PAGE_LOAD_WAIT,
)

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

# Auto-download ChromeDriver
try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

# Kafka imports
try:
    from kafka import KafkaConsumer, KafkaProducer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("⚠️  kafka-python not installed. Run: pip install kafka-python")


class BaseConsumer(ABC):
    """
    Base class cho tất cả Kafka consumers
    
    Usage:
        class MyConsumer(BaseConsumer):
            def get_worker_name(self) -> str:
                return "comment"  # hoặc "product"
            
            def get_consumer_group(self) -> str:
                return CONSUMER_GROUPS["comment_extractor"]
            
            def get_input_topic(self) -> str:
                return KAFKA_TOPICS["videos"]
            
            def get_output_topic(self) -> str:
                return KAFKA_TOPICS["comments"]
            
            def process_message(self, message: dict) -> list:
                # Process và return list of output messages
                return [{"comment": "..."}]
    """
    
    def __init__(self, use_selenium: bool = True, dry_run: bool = False):
        self.use_selenium = use_selenium
        self.dry_run = dry_run
        
        self.driver: Optional[webdriver.Chrome] = None
        self.consumer: Optional[KafkaConsumer] = None
        self.producer: Optional[KafkaProducer] = None
        
        self.running = False
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_produced": 0,
            "errors": 0,
        }
        
        # Setup signal handler
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    # ==================== ABSTRACT METHODS ====================
    
    @abstractmethod
    def get_worker_name(self) -> str:
        """Return worker name: 'scraper', 'comment', hoặc 'product'"""
        pass
    
    @abstractmethod
    def get_consumer_group(self) -> str:
        """Return Kafka consumer group ID"""
        pass
    
    @abstractmethod
    def get_input_topic(self) -> str:
        """Return input Kafka topic"""
        pass
    
    @abstractmethod
    def get_output_topic(self) -> str:
        """Return output Kafka topic"""
        pass
    
    @abstractmethod
    def process_message(self, message: dict) -> list:
        """
        Process message và return list of output messages
        
        Args:
            message: Input message dict
            
        Returns:
            List of output message dicts to produce
        """
        pass
    
    # ==================== LIFECYCLE ====================
    
    def start(self):
        """Initialize consumer, producer, and optionally Selenium"""
        worker_name = self.get_worker_name()
        profile_info = CHROME_PROFILES.get(worker_name, {})
        
        print("\n" + "="*60)
        print(f"🚀 {self.__class__.__name__}")
        print("="*60)
        print(f"   Worker: {worker_name}")
        print(f"   Chrome Profile: {profile_info.get('profile_dir', 'N/A')}")
        print(f"   Input Topic: {self.get_input_topic()}")
        print(f"   Output Topic: {self.get_output_topic()}")
        print(f"   Consumer Group: {self.get_consumer_group()}")
        print(f"   Selenium: {'Enabled' if self.use_selenium else 'Disabled'}")
        print(f"   Dry Run: {self.dry_run}")
        print("="*60)
        
        # Kafka Consumer
        if KAFKA_AVAILABLE and not self.dry_run:
            print("\n📥 Connecting to Kafka consumer...")
            # Dùng 'latest' để chỉ đọc messages mới, không đọc lại từ đầu
            self.consumer = KafkaConsumer(
                self.get_input_topic(),
                bootstrap_servers=KAFKA_BROKER,
                group_id=self.get_consumer_group(),
                auto_offset_reset="latest",  # Chỉ đọc messages mới
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                consumer_timeout_ms=5000,  # Poll timeout
            )
            print(f"   ✅ Connected to {KAFKA_BROKER}")
            print(f"   ℹ️  Reading from: LATEST (new messages only)")
        
        # Kafka Producer
        if KAFKA_AVAILABLE and not self.dry_run:
            print("📤 Connecting to Kafka producer...")
            self.producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            print(f"   ✅ Producer ready")
        
        # Selenium
        if self.use_selenium:
            print("\n🌐 Starting Chrome browser...")
            self.driver = self._create_driver()
            print(f"   ✅ Browser ready (Profile: {profile_info.get('profile_dir', 'Default')})")
            
            # Warm up
            print("🔄 Warming up TikTok...")
            self._safe_get("https://www.tiktok.com/foryou")
            print("   ✅ TikTok loaded")
        
        self.running = True
        print("\n✅ Consumer started! Waiting for messages...\n")
    
    def stop(self):
        """Cleanup resources"""
        print("\n\n🔒 Stopping consumer...")
        self.running = False
        
        if self.driver:
            print("   Closing browser...")
            try:
                self.driver.quit()
            except:
                pass
        
        if self.producer:
            print("   Flushing producer...")
            try:
                self.producer.flush(timeout=5)
                self.producer.close(timeout=5)
            except:
                pass
        
        if self.consumer:
            print("   Closing consumer...")
            try:
                self.consumer.close()
            except:
                pass
        
        # Print stats
        print("\n" + "="*60)
        print("📊 STATS")
        print("="*60)
        for key, value in self.stats.items():
            print(f"   {key}: {value}")
        print("="*60 + "\n")
    
    def run(self):
        """Main message processing loop"""
        try:
            self.start()
            
            while self.running:
                try:
                    # Poll for messages
                    if self.consumer:
                        for message in self.consumer:
                            if not self.running:
                                break
                            
                            self.stats["messages_received"] += 1
                            
                            try:
                                # Process message
                                outputs = self.process_message(message.value)
                                self.stats["messages_processed"] += 1
                                
                                # Produce outputs
                                if outputs and self.producer:
                                    for output in outputs:
                                        key = output.get("event_id", str(time.time()))
                                        self.producer.send(
                                            self.get_output_topic(),
                                            key=key,
                                            value=output,
                                        )
                                        self.stats["messages_produced"] += 1
                                    
                                    self.producer.flush()
                            
                            except Exception as e:
                                self.stats["errors"] += 1
                                self._log_error(f"Process error: {e}")
                    
                    else:
                        # Dry run mode - demo với fake message
                        if self.dry_run and self.use_selenium:
                            print("\n🧪 DRY RUN MODE - Testing with demo video...")
                            demo_message = {
                                "video_id": "demo_123",
                                "video_url": "https://www.tiktok.com/@tiktok/video/7000000000000000000",
                                "username": "tiktok",
                                "view_count": 1000000,
                                "like_count": 50000,
                                "comment_count": 1000,
                                "share_count": 500,
                            }
                            
                            try:
                                outputs = self.process_message(demo_message)
                                print(f"   ✅ Demo processed: {len(outputs)} outputs")
                                for i, out in enumerate(outputs[:3]):
                                    print(f"      [{i+1}] {str(out)[:100]}...")
                            except Exception as e:
                                print(f"   ❌ Demo error: {e}")
                            
                            # Chờ rồi chạy lại demo
                            print("\n⏳ Waiting 30s before next demo... (Ctrl+C to stop)")
                            time.sleep(30)
                        else:
                            time.sleep(1)
                
                except Exception as e:
                    if self.running:
                        self._log_error(f"Loop error: {e}")
                        time.sleep(5)
        
        finally:
            self.stop()
    
    # ==================== SELENIUM HELPERS ====================
    
    def _create_driver(self) -> webdriver.Chrome:
        """Create Chrome driver với profile riêng cho worker"""
        from pathlib import Path
        
        worker_name = self.get_worker_name()
        
        # Tạo profile riêng cho mỗi worker trong thư mục project
        # KHÔNG dùng chung với Chrome profile của user (tránh lock conflict)
        worker_profile_dir = PROJECT_ROOT / "data" / "chrome_profiles" / worker_name
        worker_profile_dir.mkdir(parents=True, exist_ok=True)
        
        options = Options()
        
        # Use separate profile directory for each worker
        options.add_argument(f"--user-data-dir={worker_profile_dir}")
        
        # Anti-detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1400,900")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--lang=vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7")
        
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
        }
        options.add_experimental_option("prefs", prefs)
        
        # Random user agent
        import random
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        ]
        options.add_argument(f"user-agent={random.choice(user_agents)}")
        
        # Auto-download ChromeDriver nếu có webdriver-manager
        if USE_WEBDRIVER_MANAGER:
            service = Service(ChromeDriverManager().install())
        else:
            service = Service(CHROME_DRIVER_PATH)
        
        driver = webdriver.Chrome(service=service, options=options)
        
        # Stealth injection
        stealth_js = """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
        """
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})
        driver.set_page_load_timeout(60)
        
        print(f"   📁 Profile: {worker_profile_dir}")
        
        return driver
    
    def _safe_get(self, url: str, max_retries: int = 3) -> bool:
        """Navigate với retry"""
        if not self.driver:
            return False
        
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                time.sleep(PAGE_LOAD_WAIT)
                self._close_popup()
                return True
            except WebDriverException as e:
                print(f"   ⚠ Error loading {url} (attempt {attempt+1}/{max_retries})")
                time.sleep(3 + attempt * 2)
        
        return False
    
    def _close_popup(self):
        """Close TikTok popups"""
        if not self.driver:
            return
        
        try:
            time.sleep(1)
            buttons = self.driver.find_elements(By.XPATH, "//button")
            for b in buttons:
                txt = (b.text or "").strip().lower()
                if any(k in txt for k in ["not now", "không phải bây giờ", "reject", "decline"]):
                    try:
                        b.click()
                        time.sleep(0.5)
                    except:
                        continue
        except:
            pass
    
    # ==================== HELPERS ====================
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n⚠️  Received stop signal...")
        self.running = False
    
    def _log_error(self, msg: str):
        """Log error to file"""
        log_file = LOG_DIR / f"{self.get_worker_name()}_errors.log"
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
        print(f"   ❌ {msg}")
