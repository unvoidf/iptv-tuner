"""
XMLTV EPG Generator
Creates dummy Electronic Program Guide for Plex setup.
"""
from datetime import datetime, timedelta
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from core.downloader import M3UChannel


class XMLTVGenerator:
    """Generates dummy XMLTV EPG data for channels."""
    
    @staticmethod
    def generate_epg(channels: List[M3UChannel]) -> str:
        """
        Generate XMLTV format EPG for given channels.
        
        Args:
            channels: List of M3UChannel objects
        
        Returns:
            XMLTV formatted string
        """
        tv = Element('tv')
        tv.set('generator-info-name', 'IPTV Tuner')
        tv.set('generator-info-url', 'http://localhost:5004')
        
        now = datetime.now()
        
        for channel in channels:
            # Add channel definition
            channel_elem = SubElement(tv, 'channel')
            channel_elem.set('id', channel.channel_id)
            
            # Smart display name: Prepend number if not already present
            # This helps Plex match channels correctly without creating "1 1 Channel" mess
            if channel.name.startswith(f"{channel.guide_number} "):
                final_name = channel.name
            elif channel.name.startswith(f"{channel.guide_number}."):
                final_name = channel.name
            else:
                final_name = f"{channel.guide_number} {channel.name}"
            
            display_name = SubElement(channel_elem, 'display-name')
            display_name.text = final_name
            
            if channel.tvg_logo:
                icon = SubElement(channel_elem, 'icon')
                icon.set('src', channel.tvg_logo)
            
            # Generate 24 hours of dummy programs
            for hour in range(24):
                program_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=hour)
                program_end = program_start + timedelta(hours=1)
                
                programme = SubElement(tv, 'programme')
                programme.set('start', program_start.strftime('%Y%m%d%H%M%S +0000'))
                programme.set('stop', program_end.strftime('%Y%m%d%H%M%S +0000'))
                programme.set('channel', channel.channel_id)
                
                title = SubElement(programme, 'title')
                title.set('lang', 'en')
                title.text = f"{channel.name} - Program {hour:02d}:00"
                
                desc = SubElement(programme, 'desc')
                desc.set('lang', 'en')
                desc.text = f"Live broadcast on {channel.name}"
                
                category = SubElement(programme, 'category')
                category.set('lang', 'en')
                category.text = channel.group_title or "General"
        
        # Pretty print XML
        rough_string = tostring(tv, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')


# Convenience function
def generate_xmltv(channels: List[M3UChannel]) -> str:
    """Generate XMLTV EPG for channel list."""
    return XMLTVGenerator.generate_epg(channels)
