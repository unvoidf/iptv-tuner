"""
Configuration Manager
Manages settings.json persistence with thread-safe operations.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Any
from threading import Lock


class ConfigManager:
    """Thread-safe configuration manager for IPTV proxy settings."""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.environ.get("CONFIG_PATH", "/app/data/settings.json")
        self.config_path = Path(config_path)
        self._lock = Lock()
        self._ensure_data_dir()
        self._load_or_create_defaults()
    
    def _ensure_data_dir(self) -> None:
        """Create data directory if it doesn't exist."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_or_create_defaults(self) -> None:
        """Load existing config or create default settings."""
        if not self.config_path.exists():
            self._settings = self._get_default_settings()
            self.save()
        else:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._settings = json.load(f)
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "m3u_url": "",
            "selected_categories": [],
            "update_interval_hours": 12,
            "kill_switch_delay_ms": 1000,
            "read_timeout_seconds": 30,
            "user_agent": "VLC/3.0.18 LibVLC/3.0.18",
            "device_id": "12345678",
            "device_name": "IPTV Tuner"
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        with self._lock:
            return self._settings.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all settings as dictionary."""
        with self._lock:
            return self._settings.copy()
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple settings and save to disk."""
        with self._lock:
            self._settings.update(updates)
            self._save_unsafe()
    
    def save(self) -> None:
        """Save current settings to disk (thread-safe)."""
        with self._lock:
            self._save_unsafe()
    
    def _save_unsafe(self) -> None:
        """Internal save method (caller must hold lock)."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._settings, f, indent=2, ensure_ascii=False)


# Global singleton instance
config = ConfigManager()
