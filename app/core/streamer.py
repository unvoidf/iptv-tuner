"""
Global Stream Manager with Kill-Switch
Ensures only one active IPTV stream at a time using async lock.
"""
import asyncio
import logging
from typing import Optional, AsyncIterator
import httpx
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Global singleton managing IPTV stream connections.
    Implements kill-switch: only one active stream allowed at any time.
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._active_client: Optional[httpx.AsyncClient] = None
        self._active_url: Optional[str] = None
    
    async def stream_channel(
        self,
        channel_url: str,
        user_agent: str,
        kill_delay_ms: int = 1000,
        read_timeout_seconds: int = 30
    ) -> StreamingResponse:
        """
        Stream a channel with kill-switch protection.
        
        Args:
            channel_url: IPTV stream URL
            user_agent: User-Agent header
            kill_delay_ms: Delay after killing previous stream (milliseconds)
            read_timeout_seconds: Per-chunk read timeout
        
        Returns:
            StreamingResponse with video content
        """
        async with self._lock:
            # Terminate any active stream
            if self._active_client:
                await self._terminate_active_stream()
                
                # Wait for IPTV provider to register disconnection
                await asyncio.sleep(kill_delay_ms / 1000.0)
                logger.info(f"Waited {kill_delay_ms}ms after stream termination")
            
            # Start new stream
            logger.info(f"Starting new stream: {channel_url[:50]}...")
            self._active_url = channel_url
            
            try:
                # Create client with timeout configuration
                timeout_config = httpx.Timeout(
                    connect=10.0,
                    read=read_timeout_seconds,
                    write=10.0,
                    pool=10.0
                )
                
                self._active_client = httpx.AsyncClient(
                    timeout=timeout_config,
                    follow_redirects=True
                )
                
                # Stream response with dynamic content type
                return StreamingResponse(
                    self._proxy_stream_async(channel_url, user_agent),
                    media_type="video/mpeg"  # Plex Live TV compatible
                )
                
            except Exception as e:
                logger.error(f"Error starting stream: {e}", exc_info=True)
                await self._cleanup_client()
                raise
    
    async def _terminate_active_stream(self) -> None:
        """Force close the active HTTP client and connection."""
        if self._active_client:
            logger.warning(f"Terminating active stream: {self._active_url}")
            try:
                await self._active_client.aclose()
            except Exception as e:
                logger.error(f"Error closing client: {e}")
            finally:
                self._active_client = None
                self._active_url = None
    
    async def _proxy_stream_async(
        self,
        url: str,
        user_agent: str
    ) -> AsyncIterator[bytes]:
        """
        Async generator that yields video chunks from IPTV source.
        
        Args:
            url: Stream URL
            user_agent: User-Agent header
        
        Yields:
            Video data chunks (8KB each)
        """
        if not self._active_client:
            raise RuntimeError("No active client available")
        
        try:
            async with self._active_client.stream(
                "GET",
                url,
                headers={"User-Agent": user_agent}
            ) as response:
                response.raise_for_status()
                
                logger.info(
                    f"Stream connected: {response.status_code}, "
                    f"Content-Type: {response.headers.get('content-type', 'unknown')}"
                )
                
                chunk_count = 0
                # Use larger chunks for better buffering (especially 4K)
                async for chunk in response.aiter_bytes(chunk_size=65536):  # 64KB chunks
                    if chunk:
                        chunk_count += 1
                        if chunk_count % 100 == 0:  # Log every ~6MB
                            logger.debug(f"Streamed {chunk_count} chunks (~{chunk_count * 64}KB)")
                        yield chunk
                
                logger.info(f"Stream completed successfully ({chunk_count} chunks)")
                
        except httpx.TimeoutException as e:
            logger.error(f"Stream timeout: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Stream request error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected stream error: {e}", exc_info=True)
            raise
        finally:
            # Cleanup on stream end
            await self._cleanup_client()
    
    async def _cleanup_client(self) -> None:
        """Close and reset active client."""
        if self._active_client:
            try:
                await self._active_client.aclose()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
            finally:
                self._active_client = None
                self._active_url = None


# Global singleton instance
stream_manager = StreamManager()
