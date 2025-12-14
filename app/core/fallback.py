"""
Fallback Video Manager for Stream Errors

Serves a dynamically generated MPEG-TS stream when IPTV streams are unavailable.
Uses FFmpeg to generate a Plex-compatible live stream with proper PAT/PMT tables.
"""
import asyncio
import logging
import subprocess
from typing import AsyncIterator

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8192  # 8KB chunks for smooth streaming


class FallbackVideoManager:
    """
    Manages fallback video streaming for unavailable channels.
    
    Uses FFmpeg to generate a live MPEG-TS stream with "Stream Not Available"
    message. This ensures proper PAT/PMT tables for Plex compatibility.
    """
    
    def __init__(self):
        self._ffmpeg_available = self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def is_available(self) -> bool:
        """Check if fallback streaming is possible."""
        return self._ffmpeg_available
    
    async def stream_fallback(self, duration_seconds: int = 300) -> AsyncIterator[bytes]:
        """
        Async generator that yields live MPEG-TS stream from FFmpeg.
        
        FFmpeg generates a black screen with "Stream Not Available" text,
        properly formatted for Plex HDHomeRun compatibility.
        
        Args:
            duration_seconds: How long to stream (default: 5 minutes)
        
        Yields:
            MPEG-TS video data chunks
        """
        if not self._ffmpeg_available:
            logger.error("FFmpeg not available for fallback streaming")
            return
        
        logger.info(f"Starting FFmpeg fallback stream (duration={duration_seconds}s)")
        
        # FFmpeg command to generate live MPEG-TS stream
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            # Input: black color source
            '-f', 'lavfi',
            '-i', f'color=c=black:s=1280x720:d={duration_seconds}:r=25',
            # Add text overlay
            '-vf', "drawtext=text='Stream Not Available':fontsize=48:fontcolor=white:x=(w-tw)/2:y=(h-th)/2",
            # Video encoding
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-b:v', '1M',
            '-g', '50',  # Keyframe every 2 seconds
            # MPEG-TS output with PAT/PMT
            '-f', 'mpegts',
            '-mpegts_flags', 'resend_headers',
            '-muxrate', '2M',
            # Output to stdout
            '-'
        ]
        
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            chunk_count = 0
            while True:
                chunk = await process.stdout.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunk_count += 1
                if chunk_count % 100 == 0:
                    logger.debug(f"Fallback stream: {chunk_count} chunks sent")
                yield chunk
            
            logger.info(f"Fallback stream completed ({chunk_count} chunks)")
            
        except asyncio.CancelledError:
            logger.info("Fallback stream cancelled by client")
        except Exception as e:
            logger.error(f"FFmpeg fallback error: {e}")
        finally:
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except Exception:
                    process.kill()


# Global singleton instance
fallback_manager = FallbackVideoManager()
