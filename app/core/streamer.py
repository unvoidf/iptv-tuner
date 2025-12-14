"""
Global Stream Manager with Kill-Switch
Ensures only one active IPTV stream at a time using async lock.
"""
import asyncio
import logging
from typing import Optional, AsyncIterator, Tuple, Union
import httpx
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class StreamUnavailableError(Exception):
    """Raised when IPTV stream returns 4xx/5xx error."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Stream unavailable ({status_code}): {message}")


class StreamManager:
    """
    Global singleton managing IPTV stream connections.
    Implements kill-switch: only one active stream allowed at any time.
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._active_client: Optional[httpx.AsyncClient] = None
        self._active_response = None
        self._active_url: Optional[str] = None
    
    async def stream_channel(
        self,
        channel_url: str,
        user_agent: str,
        kill_delay_ms: int = 1000,
        read_timeout_seconds: int = 30
    ) -> Union[StreamingResponse, None]:
        """
        Stream a channel with kill-switch protection.
        
        Probes the stream first, raises StreamUnavailableError if stream
        is not available (4xx/5xx) BEFORE returning StreamingResponse.
        
        Args:
            channel_url: IPTV stream URL
            user_agent: User-Agent header
            kill_delay_ms: Delay after killing previous stream (milliseconds)
            read_timeout_seconds: Per-chunk read timeout
        
        Returns:
            StreamingResponse with video content
            
        Raises:
            StreamUnavailableError: If stream returns 4xx/5xx error
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
                
                # PROBE THE STREAM FIRST - this is the key change
                # We initiate the connection and check status BEFORE creating StreamingResponse
                try:
                    self._active_response = await self._active_client.send(
                        self._active_client.build_request(
                            "GET",
                            channel_url,
                            headers={"User-Agent": user_agent}
                        ),
                        stream=True
                    )
                    self._active_response.raise_for_status()
                    
                    logger.info(
                        f"Stream connected: {self._active_response.status_code}, "
                        f"Content-Type: {self._active_response.headers.get('content-type', 'unknown')}"
                    )
                    
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    await e.response.aclose()
                    await self._cleanup_client()
                    
                    if 400 <= status < 500:
                        logger.warning(f"Stream unavailable ({status}): {channel_url[:60]}...")
                    else:
                        logger.error(f"Server error ({status}): {channel_url[:60]}...")
                    
                    raise StreamUnavailableError(status, str(e))
                
                # Stream is available, return the StreamingResponse
                return StreamingResponse(
                    self._stream_chunks(),
                    media_type="video/mpeg"  # Plex Live TV compatible
                )
                
            except StreamUnavailableError:
                # Re-raise for caller to handle
                raise
            except Exception as e:
                logger.error(f"Error starting stream: {e}", exc_info=True)
                await self._cleanup_client()
                raise
    
    async def _terminate_active_stream(self) -> None:
        """Force close the active HTTP client and connection."""
        if self._active_response:
            try:
                await self._active_response.aclose()
            except Exception:
                pass
            self._active_response = None
            
        if self._active_client:
            logger.warning(f"Terminating active stream: {self._active_url}")
            try:
                await self._active_client.aclose()
            except Exception as e:
                logger.error(f"Error closing client: {e}")
            finally:
                self._active_client = None
                self._active_url = None
    
    async def _stream_chunks(self) -> AsyncIterator[bytes]:
        """
        Async generator that yields video chunks from already-connected stream.
        
        Yields:
            Video data chunks (64KB each)
        """
        if not self._active_response:
            raise RuntimeError("No active response available")
        
        try:
            chunk_count = 0
            # Use larger chunks for better buffering (especially 4K)
            async for chunk in self._active_response.aiter_bytes(chunk_size=65536):
                if chunk:
                    chunk_count += 1
                    if chunk_count % 100 == 0:  # Log every ~6MB
                        logger.debug(f"Streamed {chunk_count} chunks (~{chunk_count * 64}KB)")
                    yield chunk
            
            logger.info(f"Stream completed successfully ({chunk_count} chunks)")
            
        except httpx.TimeoutException as e:
            logger.error(f"Stream timeout: {e}")
        except httpx.RequestError as e:
            logger.error(f"Stream request error: {e}")
        except Exception as e:
            logger.error(f"Unexpected stream error: {e}", exc_info=True)
        finally:
            # Cleanup on stream end
            await self._cleanup_client()
    
    async def _cleanup_client(self) -> None:
        """Close and reset active client."""
        if self._active_response:
            try:
                await self._active_response.aclose()
            except Exception:
                pass
            self._active_response = None
            
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
