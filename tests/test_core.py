import pytest
from app.core.downloader import M3UDownloader

@pytest.fixture
def sample_m3u_content():
    return """#EXTM3U
#EXTINF:-1 tvg-id="cn.science" tvg-name="Science Channel" tvg-logo="http://logo.png" group-title="Documentary",Science Channel
http://stream.url/science
#EXTINF:-1 tvg-name="Nat Geo" group-title="Documentary",Nat Geo Wild
http://stream.url/natgeo
#EXTINF:-1,Movie Channel
http://stream.url/movie
"""

def test_parse_m3u_content(sample_m3u_content):
    downloader = M3UDownloader()
    downloader._parse_m3u_content(sample_m3u_content)
    
    assert len(downloader.channels) == 3
    
    # Check first channel
    ch1 = downloader.channels[0]
    assert ch1.name == "Science Channel"
    assert ch1.group_title == "Documentary"
    assert ch1.url == "http://stream.url/science"
    assert ch1.tvg_logo == "http://logo.png"
    
    # Check second channel (verifying name parsing)
    ch2 = downloader.channels[1]
    # In this case, the name after comma "Nat Geo Wild" is clean, so it is used.
    assert ch2.name == "Nat Geo Wild"
    assert ch2.group_title == "Documentary"
    
    # Check third channel (simple format)
    ch3 = downloader.channels[2]
    assert ch3.name == "Movie Channel"
    assert ch3.group_title == "Uncategorized"

def test_category_filtering(sample_m3u_content):
    downloader = M3UDownloader()
    downloader._parse_m3u_content(sample_m3u_content)
    
    # Test filtering logic (mimicking download_and_parse)
    selected = ["Documentary"]
    filtered = [ch for ch in downloader.channels if ch.group_title in selected]
    
    assert len(filtered) == 2
    assert filtered[0].name == "Science Channel"
    assert filtered[1].name == "Nat Geo Wild"
    
    # Test empty filter (should return all if we were using the main method, 
    # but here we are testing the list directly)
    assert len(downloader.channels) == 3
