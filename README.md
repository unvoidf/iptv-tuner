# IPTV Tuner

Docker-based IPTV proxy that emulates HDHomeRun for safe single-connection streaming in Plex, Jellyfin, and Emby.

## 🎯 Features

- **Kill-Switch Protection**: Automatically terminates old streams before starting new ones
- **HDHomeRun Emulation**: Recognized by Plex as a local tuner device
- **Fallback Video**: Shows "Stream Not Available" when channels are offline (e.g., match-time only channels)
- **Async Streaming**: Non-blocking I/O with httpx for performance
- **Stall Protection**: Configurable read timeout prevents hung connections
- **Category Filtering**: Select which M3U groups to include
- **Auto-Updates**: Scheduled M3U playlist refresh
- **Web Interface**: Dark mode management panel

## 🚀 Quick Start

### 1. Installation

#### Option A: Docker Image (Recommended)
Create a `docker-compose.yml` file:

```yaml
version: '3.8'
services:
  iptv-tuner:
    image: ghcr.io/unvoidf/iptv-tuner:latest
    container_name: iptv-tuner
    restart: unless-stopped
    ports:
      - "5004:5004"
    volumes:
      - ./data:/app/data
    environment:
      - PORT=5004
      # BASE_URL Configuration:
      # - Use 'http://localhost:5004' if Plex/Jellyfin is on the same machine (Host Mode)
      # - Use LAN IP (e.g., 'http://192.168.1.50:5004') if running in Bridge Mode or on separate devices
      - BASE_URL=http://localhost:5004
```

Then run:
```bash
docker-compose up -d
```

#### Option B: Build from Source
```bash
git clone https://github.com/unvoidf/iptv-tuner.git
cd iptv-tuner
docker-compose up -d --build
```

### 2. Configure

Open http://localhost:5004 in your browser:

1. Enter your M3U playlist URL
2. Set User-Agent (default: VLC/3.0.18)
3. Adjust kill-switch delay (default: 1000ms)
4. Select channel categories
5. Click **Save**

### 3. Add to Media Server
#### Plex
1. Open Plex Settings → Live TV & DVR
2. Click **Setup Plex DVR**
3. Plex should auto-discover "IPTV Tuner" (click it)
4. When asked for EPG, select **"Have XMLTV Guide"**
5. Enter: `http://localhost:5004/epg.xml` (or your LAN IP)
6. Click **Continue** to map channels

#### Jellyfin / Emby
1. Go to Dashboard → Live TV → Tuner Devices
2. Click **+** (Add) and select "HDHomeRun" (if not auto-discovered)
3. Enter Tuner URL: `http://localhost:5004`
4. Under **TV Guide Data Providers**, click **+** (Add) → **XMLTV**
5. Enter File/URL: `http://localhost:5004/epg.xml`

## ⚙️ Configuration

### Environment Variables

- `PORT`: Server port (default: 5004)
- `BASE_URL`: Base URL for lineup (default: http://localhost:5004)

### Settings (via Web UI)

- **M3U URL**: Your IPTV playlist URL
- **User-Agent**: HTTP header sent to IPTV provider
- **Kill-Switch Delay**: Wait time after terminating old stream (200-3000ms)
- **Read Timeout**: Per-chunk timeout for stall detection (10-60s)
- **Update Interval**: Automatic M3U refresh frequency (6-48 hours)

## 📁 Project Structure

```
iptv-tuner/
├── app/
│   ├── main.py              # FastAPI app & HDHomeRun endpoints
│   ├── config.py            # Settings manager
│   ├── core/
│   │   ├── downloader.py    # M3U parser
│   │   ├── streamer.py      # Kill-switch streaming
│   │   ├── fallback.py      # Fallback video generator
│   │   └── xmltv.py         # EPG generator
│   ├── api/
│   │   └── routes.py        # Management API
│   └── templates/
│       └── index.html       # Web UI
├── data/                    # Persistent storage (volume)
│   └── settings.json
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 🔧 API Endpoints

### HDHomeRun Emulation
- `GET /discover.json` - Device discovery
- `GET /lineup.json` - Channel list
- `GET /epg.xml` - XMLTV EPG
- `GET /stream/{channel_id}` - Stream proxy

### Management API
- `GET /api/settings` - Get current settings
- `POST /api/settings` - Update settings
- `GET /api/categories` - List M3U categories
- `POST /api/refresh` - Force M3U update
- `GET /health` - Health check

## 🛠️ Development

### Local Run (without Docker)

```bash
cd iptv-tuner
pip install -r requirements.txt
cd app
uvicorn main:app --reload --port 5004
```

### View Logs

```bash
docker-compose logs -f iptv-tuner
```

### Rebuild Container

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## ⚠️ Important Notes

1. **Single Connection Limit**: This proxy is designed for IPTV providers that allow only 1 concurrent connection
2. **Network Configuration (BASE_URL)**:
   - **Host Mode / Non-Docker**: If your Media Server (Plex/Jellyfin) is on the same machine and uses `network_mode: host` (or runs natively), you can use `http://localhost:5004`.
   - **Bridge Mode / Separate Device**: If your Media Server is in a Docker container (bridge mode) or on a different device, you **MUST** set `BASE_URL` to your server's LAN IP (e.g., `http://192.168.1.50:5004`).
3. **User-Agent**: Some providers may block requests - adjust User-Agent if needed

## 🚧 Known Issues & Roadmap

- **M3U Compatibility**: Supports **M3U Plus** playlists (commonly generated by Xtream Codes via `get.php?type=m3u_plus`). Direct Xtream Codes login (Host/User/Pass) is not supported; you must use the full M3U URL.
- **Plex Category Refresh**: When adding *new* categories in the proxy settings, Plex often requires removing and re-adding the DVR tuner to recognize the new channels. This appears to be a Plex behavior, but if you know a workaround, please open an issue or PR!
- **Jellyfin / Emby Support**: Theoretically compatible via HDHomeRun emulation, but currently **experimental** and primarily tested on Plex. Feedback is welcome!

## 📝 License

MIT License - Free for personal use
