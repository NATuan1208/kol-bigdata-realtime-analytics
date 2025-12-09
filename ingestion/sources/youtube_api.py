"""
YouTube API Client

Wrapper cho YouTube Data API v3 để lấy:
- Channel info (subscribers, total views, videos)
- Video list (top videos của channel)
- Video stats (views, likes, comments)
- Comments (top comments của video)

Setup:
1. Google Cloud Console: https://console.cloud.google.com
2. Enable YouTube Data API v3
3. Create API Key
4. Set YOUTUBE_API_KEY environment variable

Usage:
    from ingestion.sources.youtube_api import YouTubeAPI
    
    api = YouTubeAPI(api_key="AIzaSy...")
    channel = api.get_channel_info("UCX6OQ3DkcsbYNE6H8uQQuVA")
    videos = api.get_channel_videos("UCX6OQ3DkcsbYNE6H8uQQuVA", max_results=50)
    stats = api.get_video_stats(["video_id1", "video_id2"])
    comments = api.get_comments("video_id", max_results=100)
"""

import os
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("⚠️  google-api-python-client not installed!")
    print("   Install: pip install google-api-python-client")


@dataclass
class YouTubeChannel:
    """YouTube Channel Info"""
    channel_id: str
    username: str  # @handle or custom URL
    title: str
    subscribers: int
    total_videos: int
    total_views: int
    description: str
    avatar_url: str
    published_at: str


@dataclass
class YouTubeVideo:
    """YouTube Video Stats"""
    video_id: str
    channel_id: str
    username: str
    title: str
    description: str
    view_count: int
    like_count: int
    comment_count: int
    duration: int  # seconds
    published_at: str
    thumbnail_url: str


@dataclass
class YouTubeComment:
    """YouTube Comment"""
    comment_id: str
    video_id: str
    username: str  # channel username
    author: str  # commenter name
    text: str
    like_count: int
    published_at: str


class YouTubeAPI:
    """YouTube Data API v3 Client"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY not found in environment!")
        
        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        self.quota_used = 0  # Track quota usage (approximation)
    
    def get_channel_by_handle(self, handle: str) -> Optional[YouTubeChannel]:
        """
        Get channel info by @handle (username)
        
        Quota cost: 1 unit
        Uses forHandle parameter to find channel by @username
        
        Args:
            handle: Channel handle without @ (e.g., "mrbeast" not "@mrbeast")
        
        Returns:
            YouTubeChannel or None if not found
        """
        try:
            # Clean handle - remove @ if present
            clean_handle = handle.replace('@', '').strip()
            
            response = self.youtube.channels().list(
                part='snippet,statistics',
                forHandle=clean_handle
            ).execute()
            
            self.quota_used += 1
            
            if not response.get('items'):
                return None
            
            item = response['items'][0]
            snippet = item['snippet']
            stats = item['statistics']
            channel_id = item['id']
            
            # Get username from customUrl
            username = snippet.get('customUrl', '').replace('@', '')
            if not username:
                username = clean_handle
            
            return YouTubeChannel(
                channel_id=channel_id,
                username=username,
                title=snippet['title'],
                subscribers=int(stats.get('subscriberCount', 0)),
                total_videos=int(stats.get('videoCount', 0)),
                total_views=int(stats.get('viewCount', 0)),
                description=snippet.get('description', ''),
                avatar_url=snippet['thumbnails']['high']['url'],
                published_at=snippet['publishedAt']
            )
        
        except HttpError as e:
            print(f"   ❌ YouTube API error (get_channel_by_handle): {e}")
            return None
    
    def get_channel_info(self, channel_id: str) -> Optional[YouTubeChannel]:
        """
        Get channel info by channel_id
        
        Quota cost: 1 unit
        """
        try:
            response = self.youtube.channels().list(
                part='snippet,statistics',
                id=channel_id
            ).execute()
            
            self.quota_used += 1
            
            if not response.get('items'):
                return None
            
            item = response['items'][0]
            snippet = item['snippet']
            stats = item['statistics']
            
            # Try to get @handle from customUrl
            username = snippet.get('customUrl', '').replace('@', '')
            if not username:
                username = snippet['title'].replace(' ', '').lower()
            
            return YouTubeChannel(
                channel_id=channel_id,
                username=username,
                title=snippet['title'],
                subscribers=int(stats.get('subscriberCount', 0)),
                total_videos=int(stats.get('videoCount', 0)),
                total_views=int(stats.get('viewCount', 0)),
                description=snippet.get('description', ''),
                avatar_url=snippet['thumbnails']['high']['url'],
                published_at=snippet['publishedAt']
            )
        
        except HttpError as e:
            print(f"   ❌ YouTube API error: {e}")
            return None
    
    def get_channel_videos(self, channel_id: str, max_results: int = 50) -> List[str]:
        """
        Get latest video IDs from channel
        
        Quota cost: 100 units (search.list)
        Returns: List of video IDs
        """
        try:
            response = self.youtube.search().list(
                part='id',
                channelId=channel_id,
                order='date',  # Latest first
                type='video',
                maxResults=min(max_results, 50)  # API limit 50
            ).execute()
            
            self.quota_used += 100
            
            video_ids = [item['id']['videoId'] for item in response.get('items', [])]
            return video_ids
        
        except HttpError as e:
            print(f"   ❌ YouTube API error: {e}")
            return []
    
    def get_video_stats(self, video_ids: List[str]) -> List[YouTubeVideo]:
        """
        Get video stats for multiple videos
        
        Quota cost: 1 unit per call (can fetch up to 50 videos per call)
        """
        if not video_ids:
            return []
        
        videos = []
        
        # API allows max 50 video IDs per call
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            
            try:
                response = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(batch)
                ).execute()
                
                self.quota_used += 1
                
                for item in response.get('items', []):
                    snippet = item['snippet']
                    stats = item['statistics']
                    content = item['contentDetails']
                    
                    # Parse duration PT1M30S → 90 seconds
                    duration = self._parse_duration(content['duration'])
                    
                    videos.append(YouTubeVideo(
                        video_id=item['id'],
                        channel_id=snippet['channelId'],
                        username='',  # Will be set by worker
                        title=snippet['title'],
                        description=snippet.get('description', ''),
                        view_count=int(stats.get('viewCount', 0)),
                        like_count=int(stats.get('likeCount', 0)),
                        comment_count=int(stats.get('commentCount', 0)),
                        duration=duration,
                        published_at=snippet['publishedAt'],
                        thumbnail_url=snippet['thumbnails']['high']['url']
                    ))
            
            except HttpError as e:
                print(f"   ❌ YouTube API error: {e}")
                continue
            
            time.sleep(0.1)  # Rate limiting
        
        return videos
    
    def get_comments(self, video_id: str, max_results: int = 100) -> List[YouTubeComment]:
        """
        Get top comments for a video
        
        Quota cost: 1 unit
        """
        try:
            response = self.youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                order='relevance',  # Top comments
                maxResults=min(max_results, 100)  # API limit 100
            ).execute()
            
            self.quota_used += 1
            
            comments = []
            for item in response.get('items', []):
                snippet = item['snippet']['topLevelComment']['snippet']
                
                comments.append(YouTubeComment(
                    comment_id=item['id'],
                    video_id=video_id,
                    username='',  # Will be set by worker
                    author=snippet['authorDisplayName'],
                    text=snippet['textDisplay'][:1000],  # Limit length
                    like_count=int(snippet.get('likeCount', 0)),
                    published_at=snippet['publishedAt']
                ))
            
            return comments
        
        except HttpError as e:
            # Comments might be disabled
            if e.resp.status == 403:
                return []
            print(f"   ❌ YouTube API error: {e}")
            return []
    
    def _parse_duration(self, duration_str: str) -> int:
        """
        Parse ISO 8601 duration to seconds
        PT1H2M30S → 3750 seconds
        """
        import re
        
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds
    
    def get_quota_used(self) -> int:
        """Get approximate quota used in this session"""
        return self.quota_used


# Test
if __name__ == "__main__":
    api = YouTubeAPI()
    
    # Test channel info
    print("Testing channel info...")
    channel = api.get_channel_info("UCX6OQ3DkcsbYNE6H8uQQuVA")  # MrBeast
    if channel:
        print(f"✅ Channel: {channel.title}")
        print(f"   Subscribers: {channel.subscribers:,}")
        print(f"   Videos: {channel.total_videos:,}")
    
    # Test videos
    print("\nTesting videos...")
    video_ids = api.get_channel_videos("UCX6OQ3DkcsbYNE6H8uQQuVA", max_results=5)
    print(f"✅ Found {len(video_ids)} videos")
    
    if video_ids:
        videos = api.get_video_stats(video_ids[:3])
        for v in videos:
            print(f"   📹 {v.title[:50]}... - {v.view_count:,} views")
    
    print(f"\n📊 Quota used: {api.get_quota_used()} units")
