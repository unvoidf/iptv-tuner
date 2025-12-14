import sys
import os
from pathlib import Path

# Add the app directory to sys.path so that "from config import config" works
app_path = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_path))

# Set config path to a temp file for tests (in tests/ directory)
test_config_path = Path(__file__).parent / "test_settings.json"
os.environ["CONFIG_PATH"] = str(test_config_path)
