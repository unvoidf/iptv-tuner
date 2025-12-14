FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install FFmpeg and fonts for fallback video generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /app/

# Create directories
RUN mkdir -p /app/data /app/assets

# Generate offline fallback video (MPEG-TS with PAT/PMT for Plex HDHomeRun compatibility)
RUN ffmpeg -f lavfi -i color=c=black:s=1280x720:d=5 \
    -vf "drawtext=text='Stream Not Available':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:fontsize=48:fontcolor=white:x=(w-tw)/2:y=(h-th)/2" \
    -c:v libx264 -preset ultrafast -b:v 1M \
    -f mpegts -mpegts_flags resend_headers \
    -y /app/assets/offline.ts

# Expose port
EXPOSE 5004

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5004"]
