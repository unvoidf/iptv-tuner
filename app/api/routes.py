"""
Management API Routes
Internal API for Web UI configuration and control.
"""
import logging
from typing import Dict, List, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import config
from core.downloader import M3UDownloader

logger = logging.getLogger(__name__)
router = APIRouter()

# Global M3U downloader instance (shared with main.py)
m3u_downloader: M3UDownloader = None

# Callback function to update main app's channel list
update_channels_callback = None


def set_downloader(downloader: M3UDownloader):
    """Set the global downloader instance (called from main.py)."""
    global m3u_downloader
    m3u_downloader = downloader


def set_update_callback(callback):
    """Set callback to update main app's current_channels."""
    global update_channels_callback
    update_channels_callback = callback


class SettingsUpdate(BaseModel):
    """Request model for settings updates."""
    m3u_url: str = None
    selected_categories: List[str] = None
    update_interval_hours: int = None
    kill_switch_delay_ms: int = None
    read_timeout_seconds: int = None
    user_agent: str = None


@router.get("/api/settings")
async def get_settings() -> Dict[str, Any]:
    """Get current application settings."""
    return config.get_all()


@router.post("/api/settings")
async def update_settings(settings: SettingsUpdate) -> Dict[str, str]:
    """
    Update application settings.
    Triggers M3U reload if URL or categories changed.
    """
    updates = {}
    
    if settings.m3u_url is not None:
        updates["m3u_url"] = settings.m3u_url
    if settings.selected_categories is not None:
        updates["selected_categories"] = settings.selected_categories
    if settings.update_interval_hours is not None:
        updates["update_interval_hours"] = settings.update_interval_hours
    if settings.kill_switch_delay_ms is not None:
        updates["kill_switch_delay_ms"] = settings.kill_switch_delay_ms
    if settings.read_timeout_seconds is not None:
        updates["read_timeout_seconds"] = settings.read_timeout_seconds
    if settings.user_agent is not None:
        updates["user_agent"] = settings.user_agent
    
    if updates:
        config.update(updates)
        logger.info(f"Settings updated: {list(updates.keys())}")
        
        # Reload M3U if URL or categories changed
        if "m3u_url" in updates or "selected_categories" in updates:
            await _reload_m3u()
    
    return {"status": "ok", "message": "Settings updated successfully"}


@router.get("/api/categories")
async def get_categories() -> List[str]:
    """Get list of all available categories from current M3U."""
    if not m3u_downloader:
        return []
    
    return m3u_downloader.get_all_categories()


@router.post("/api/refresh")
async def force_refresh() -> Dict[str, str]:
    """Force immediate M3U download and parse."""
    try:
        await _reload_m3u()
        return {"status": "ok", "message": "M3U refreshed successfully"}
    except Exception as e:
        logger.error(f"Error refreshing M3U: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _reload_m3u():
    """Internal helper to reload M3U playlist."""
    global update_channels_callback
    
    if not m3u_downloader:
        raise HTTPException(status_code=500, detail="Downloader not initialized")
    
    m3u_url = config.get("m3u_url")
    user_agent = config.get("user_agent")
    selected_categories = config.get("selected_categories")
    
    if not m3u_url:
        logger.warning("M3U URL not configured, skipping reload")
        return
    
    logger.info("Reloading M3U playlist...")
    channels = await m3u_downloader.download_and_parse(
        m3u_url=m3u_url,
        user_agent=user_agent,
        selected_categories=selected_categories if selected_categories else None
    )
    
    # Update main app's current_channels via callback
    if update_channels_callback:
        update_channels_callback(channels)
        logger.info(f"M3U reload complete - {len(channels)} channels")
    else:
        logger.warning("M3U reload complete but no callback registered")

