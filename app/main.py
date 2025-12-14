"""
FastAPI Main Application
HDHomeRun emulation endpoints and IPTV streaming proxy.
"""
import logging
import os
from typing import List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from core.downloader import M3UDownloader, M3UChannel
from core.streamer import stream_manager
from core.xmltv import generate_xmltv
from api import routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
m3u_downloader = M3UDownloader()
scheduler = AsyncIOScheduler()
current_channels: List[M3UChannel] = []


async def update_m3u_task():
    """Scheduled task to update M3U playlist."""
    global current_channels
    
    m3u_url = config.get("m3u_url")
    if not m3u_url:
        logger.warning("M3U URL not configured, skipping scheduled update")
        return
    
    try:
        logger.info("Running scheduled M3U update...")
        user_agent = config.get("user_agent")
        selected_categories = config.get("selected_categories") or []
        
        channels = await m3u_downloader.download_and_parse(
            m3u_url=m3u_url,
            user_agent=user_agent,
            selected_categories=selected_categories if selected_categories else None
        )
        
        current_channels = channels
        
        # Cleanup orphan categories (categories that no longer exist in M3U)
        available_categories = set(m3u_downloader.get_all_categories())
        valid_categories = [cat for cat in selected_categories if cat in available_categories]
        
        if len(valid_categories) < len(selected_categories):
            orphan_count = len(selected_categories) - len(valid_categories)
            logger.info(f"Cleaned up {orphan_count} orphan categories from settings")
            config.update({"selected_categories": valid_categories})
        
        logger.info(f"Scheduled update complete: {len(current_channels)} channels loaded")
        
    except Exception as e:
        logger.error(f"Error in scheduled M3U update: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""
    # Startup
    logger.info("Starting IPTV Tuner...")
    
    # Set downloader in routes module
    routes.set_downloader(m3u_downloader)
    
    # Register callback to update current_channels
    def update_channels(channels):
        global current_channels
        current_channels = channels
        logger.info(f"Channel list updated: {len(current_channels)} channels")
    
    routes.set_update_callback(update_channels)
    
    # Initial M3U load
    await update_m3u_task()
    
    # Schedule periodic updates
    update_interval = config.get("update_interval_hours", 12)
    scheduler.add_job(
        update_m3u_task,
        'interval',
        hours=update_interval,
        id='m3u_update'
    )
    scheduler.start()
    logger.info(f"Scheduled M3U updates every {update_interval} hours")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    scheduler.shutdown()


# Create FastAPI app
app = FastAPI(
    title="IPTV Tuner",
    description="HDHomeRun emulator for IPTV with kill-switch protection",
    version="1.0.0",
    lifespan=lifespan
)

# Include management API routes
app.include_router(routes.router)


@app.get("/")
async def serve_frontend():
    """Serve the Web UI."""
    return FileResponse("/app/templates/index.html")


@app.get("/discover.json")
async def discover() -> Dict:
    """HDHomeRun discovery endpoint for Plex."""
    device_id = config.get("device_id", "12345678")
    device_name = config.get("device_name", "IPTV Tuner")
    
    # Get base URL from environment or use default
    base_url = os.environ.get("BASE_URL", "http://localhost:5004")
    
    return {
        "FriendlyName": device_name,
        "ModelNumber": "HDHR4-2US",
        "FirmwareName": "hdhomerun4_atsc",
        "TunerCount": 1,
        "FirmwareVersion": "20190621",
        "DeviceID": device_id,
        "DeviceAuth": "test1234",
        "BaseURL": base_url,
        "LineupURL": f"{base_url}/lineup.json"
    }


@app.get("/lineup_status.json")
async def lineup_status() -> Dict:
    """HDHomeRun lineup status endpoint."""
    return {
        "ScanInProgress": 0,
        "ScanPossible": 1,
        "Source": "Cable",
        "SourceList": ["Cable"]
    }


@app.post("/lineup.post")
async def lineup_post(request: Request):
    """
    HDHomeRun lineup scan endpoint.
    Plex uses this to start/stop channel scans.
    We don't actually scan (M3U is static), so just return success.
    """
    params = dict(request.query_params)
    logger.info(f"Lineup scan request: {params}")
    
    # Return empty 200 OK (scan not needed for M3U)
    return {}



@app.get("/lineup.json")
async def get_lineup() -> List[Dict]:
    """
    HDHomeRun channel lineup endpoint.
    Returns filtered channels in Plex-compatible format.
    """
    base_url = os.environ.get("BASE_URL", "http://localhost:5004")
    
    lineup = []
    for channel in current_channels:
        lineup.append({
            "GuideNumber": channel.guide_number,
            "GuideName": f"{channel.guide_number} {channel.name}",
            "URL": f"{base_url}/stream/{channel.channel_id}"
        })
    
    logger.info(f"Lineup request: returning {len(lineup)} channels")
    return lineup


@app.get("/epg.xml")
async def get_epg(request: Request) -> Response:
    """
    XMLTV EPG endpoint for Plex.
    Accepts optional ?v=X parameter to force refresh (e.g., ?v=2)
    """
    xmltv_content = generate_xmltv(current_channels)
    
    # Generate timestamp to bust Plex EPG cache
    from datetime import datetime
    timestamp = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    # Get version from query params (for manual cache busting)
    version = request.query_params.get("v", "1")
    
    return Response(
        content=xmltv_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": "inline; filename=epg.xml",
            "Last-Modified": timestamp,
            "Cache-Control": "no-cache, must-revalidate",
            "ETag": f'"{len(current_channels)}-{version}"'
        }
    )


@app.get("/stream/{channel_id}")
async def stream_channel(channel_id: str):
    """
    Stream a specific channel (proxy to IPTV source).
    Implements kill-switch: terminates any active stream before starting new one.
    Falls back to offline test card if stream is unavailable.
    """
    from core.streamer import StreamUnavailableError
    from core.fallback import fallback_manager
    from fastapi.responses import StreamingResponse
    
    # Find channel
    channel = next((ch for ch in current_channels if ch.channel_id == channel_id), None)
    
    if not channel:
        logger.error(f"Channel not found: {channel_id}")
        raise HTTPException(status_code=404, detail="Channel not found")
    
    logger.info(f"Stream request for: {channel.name} ({channel_id})")
    
    try:
        # Get streaming parameters from config
        user_agent = config.get("user_agent")
        kill_delay_ms = config.get("kill_switch_delay_ms", 1000)
        read_timeout = config.get("read_timeout_seconds", 30)
        
        # Delegate to stream manager (with kill-switch)
        return await stream_manager.stream_channel(
            channel_url=channel.url,
            user_agent=user_agent,
            kill_delay_ms=kill_delay_ms,
            read_timeout_seconds=read_timeout
        )
        
    except StreamUnavailableError as e:
        # Serve fallback video for unavailable streams (403, 404, etc.)
        logger.info(f"Serving fallback for: {channel.name} (status={e.status_code})")
        
        if fallback_manager.is_available():
            return StreamingResponse(
                fallback_manager.stream_fallback(),
                media_type="video/mpeg"  # MPEG-TS for Plex compatibility
            )
        else:
            # No fallback available, return HTTP error
            raise HTTPException(
                status_code=503,
                detail="Stream temporarily unavailable"
            )
    
    except Exception as e:
        logger.error(f"Stream error for {channel_id}: {e}", exc_info=True)
        
        # Return appropriate HTTP error
        if "timeout" in str(e).lower():
            raise HTTPException(status_code=504, detail="Gateway timeout")
        else:
            raise HTTPException(status_code=502, detail="Bad gateway")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "channels_loaded": len(current_channels),
        "m3u_url_configured": bool(config.get("m3u_url"))
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5004))
    uvicorn.run(app, host="0.0.0.0", port=port)
