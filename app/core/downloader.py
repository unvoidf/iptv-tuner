"""
M3U Downloader and Parser
Asynchronously downloads and filters M3U playlists.
"""
import re
import logging
from typing import List, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


class M3UChannel:
    """Represents a single IPTV channel."""
    
    def __init__(
        self,
        channel_id: str,
        name: str,
        url: str,
        group_title: str = "",
        tvg_name: str = "",
        tvg_logo: str = "",
        guide_number: str = ""
    ):
        self.channel_id = channel_id
        self.name = name
        self.url = url
        self.group_title = group_title
        self.tvg_name = tvg_name
        self.tvg_logo = tvg_logo
        self.guide_number = guide_number
    
    def to_dict(self) -> Dict:
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "url": self.url,
            "group_title": self.group_title,
            "tvg_name": self.tvg_name,
            "tvg_logo": self.tvg_logo,
            "guide_number": self.guide_number
        }


class M3UDownloader:
    """Async M3U playlist downloader and parser."""
    
    # Regex patterns for extracting individual attributes
    TVG_NAME_PATTERN = re.compile(r'tvg-name="([^"]*)"', re.IGNORECASE)
    TVG_LOGO_PATTERN = re.compile(r'tvg-logo="([^"]*)"', re.IGNORECASE)
    GROUP_TITLE_PATTERN = re.compile(r'group-title="([^"]*)"', re.IGNORECASE)
    CHANNEL_NAME_PATTERN = re.compile(r',\s*(.+)$')
    
    # Content type emojis
    CONTENT_TYPE_EMOJI = {
        "live": "📡",
        "movie": "🎬",
        "series": "📺"
    }
    
    def __init__(self):
        self.channels: List[M3UChannel] = []
        self.all_categories: set = set()
        self.category_types: Dict[str, str] = {}  # category -> content type
    
    async def download_and_parse(
        self,
        m3u_url: str,
        user_agent: str,
        selected_categories: Optional[List[str]] = None
    ) -> List[M3UChannel]:
        """
        Download M3U from URL and parse channels.
        
        Args:
            m3u_url: URL to M3U playlist
            user_agent: User-Agent header for request
            selected_categories: List of group-title values to include (None = all)
        
        Returns:
            List of filtered M3UChannel objects
        """
        if not m3u_url:
            logger.warning("M3U URL is empty, returning empty channel list")
            return []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Downloading M3U from: {m3u_url}")
                response = await client.get(
                    m3u_url,
                    headers={"User-Agent": user_agent},
                    follow_redirects=True
                )
                response.raise_for_status()
                content = response.text
                
            logger.info(f"Downloaded {len(content)} bytes, parsing...")
            self._parse_m3u_content(content)
            
            # Filter by categories if specified
            if selected_categories:
                filtered = [
                    ch for ch in self.channels
                    if ch.group_title in selected_categories
                ]
                logger.info(
                    f"Filtered {len(filtered)}/{len(self.channels)} channels "
                    f"by categories: {selected_categories}"
                )
                return filtered
            
            logger.info(f"Returning all {len(self.channels)} channels (no filter)")
            return self.channels
            
        except httpx.TimeoutException:
            logger.error(f"Timeout downloading M3U from {m3u_url}")
            return []
        except httpx.RequestError as e:
            logger.error(f"Error downloading M3U: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing M3U: {e}", exc_info=True)
            return []
    
    def _parse_m3u_content(self, content: str) -> None:
        """Parse M3U content and populate channels list."""
        self.channels.clear()
        self.all_categories.clear()
        self.category_types.clear()
        
        lines = content.splitlines()
        channel_counter = 1
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for EXTINF lines
            if line.startswith("#EXTINF"):
                # Next non-empty line should be the URL
                url = None
                for j in range(i + 1, min(i + 5, len(lines))):
                    potential_url = lines[j].strip()
                    if potential_url and not potential_url.startswith("#"):
                        url = potential_url
                        i = j  # Skip to URL line
                        break
                
                if not url:
                    i += 1
                    continue
                
                # Extract attributes using individual regex patterns
                tvg_name_match = self.TVG_NAME_PATTERN.search(line)
                tvg_logo_match = self.TVG_LOGO_PATTERN.search(line)
                group_title_match = self.GROUP_TITLE_PATTERN.search(line)
                
                tvg_name = tvg_name_match.group(1) if tvg_name_match else ""
                tvg_logo = tvg_logo_match.group(1) if tvg_logo_match else ""
                group_title = group_title_match.group(1) if group_title_match else "Uncategorized"
                
                # Extract channel name from after the last comma
                # Handle cases where EXTINF content is duplicated after comma
                if ',' in line:
                    # Split by comma and get the last part
                    parts = line.split(',')
                    channel_name = parts[-1].strip()
                    
                    # If channel name looks like it has attributes (contains tvg-), use tvg-name instead
                    if 'tvg-' in channel_name or '="' in channel_name:
                        channel_name = tvg_name if tvg_name else f"Channel {channel_counter}"
                else:
                    channel_name = tvg_name if tvg_name else f"Channel {channel_counter}"
                
                # Create channel object
                channel = M3UChannel(
                    channel_id=f"ch{channel_counter}",
                    name=channel_name,
                    url=url,
                    group_title=group_title,
                    tvg_name=tvg_name or channel_name,
                    tvg_logo=tvg_logo,
                    guide_number=str(channel_counter)
                )
                
                self.channels.append(channel)
                self.all_categories.add(group_title)
                
                # Detect and store content type for this category
                content_type = self._detect_content_type(url)
                if group_title not in self.category_types:
                    self.category_types[group_title] = content_type
                
                channel_counter += 1
            
            i += 1
        
        logger.info(
            f"Parsed {len(self.channels)} channels, "
            f"{len(self.all_categories)} unique categories"
        )
    
    def get_all_categories(self) -> List[str]:
        """Get sorted list of all discovered categories."""
        return sorted(list(self.all_categories))
    
    def get_categories_with_types(self) -> List[Dict[str, str]]:
        """
        Get categories with content type indicators.
        
        Returns:
            List of dicts with 'name', 'type', and 'display' (name + emoji)
        """
        result = []
        for category in sorted(self.all_categories):
            content_type = self.category_types.get(category, "live")
            emoji = self.CONTENT_TYPE_EMOJI.get(content_type, "📡")
            result.append({
                "name": category,
                "type": content_type,
                "display": f"{category} {emoji}"
            })
        return result
    
    @staticmethod
    def _detect_content_type(url: str) -> str:
        """
        Detect content type from URL pattern.
        
        Returns:
            'movie', 'series', or 'live'
        """
        url_lower = url.lower()
        if "/movie/" in url_lower:
            return "movie"
        elif "/series/" in url_lower:
            return "series"
        else:
            return "live"
