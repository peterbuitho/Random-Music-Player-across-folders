import os
from mutagen import File
import os

import musicbrainzngs

def fetch_metadata_preview(filepath, tags=None):
    """
    Fetch missing metadata (year, artist, album, title) from MusicBrainz for preview only.
    Returns a dict of fetched tags (does not save to file or cache).
    """
    from mutagen import File
    if tags is None:
        tags = {}
        try:
            audio = File(filepath)
            if audio is not None and hasattr(audio, 'tags') and audio.tags is not None:
                for tag in ["title", "artist", "album", "year"]:
                    for key in audio.tags.keys():
                        if key.lower() == tag:
                            v = audio.tags[key]
                            tags[tag] = str(v[0]) if isinstance(v, list) else str(v)
        except Exception:
            pass
    musicbrainzngs.set_useragent("MusicPlayerGradio", "1.0", "https://github.com/yourusername/yourrepo")
    title = tags.get('title')
    artist = tags.get('artist')
    album = tags.get('album')
    year = tags.get('year')
    if title and artist and album and year:
        return tags  # Nothing missing
    query = []
    if title:
        query.append(f'track:{title}')
    if artist:
        query.append(f'artist:{artist}')
    if album:
        query.append(f'release:{album}')
    query_str = ' AND '.join(query)
    if not query_str:
        return tags
    try:
        result = musicbrainzngs.search_recordings(query=query_str, limit=1)
        if result['recording-list']:
            rec = result['recording-list'][0]
            # Preview: only add missing tags
            if not year:
                date = rec.get('first-release-date')
                if (not date or not date.strip()) and 'release-list' in rec and rec['release-list']:
                    for release in rec['release-list']:
                        release_date = release.get('date')
                        if release_date and release_date.strip():
                            date = release_date
                            break
                if date and date.strip():
                    try:
                        tags['year'] = int(date[:4])
                    except Exception:
                        pass
            if not title and rec.get('title'):
                tags['title'] = rec['title']
            if not artist and 'artist-credit' in rec and rec['artist-credit']:
                tags['artist'] = rec['artist-credit'][0]['artist']['name']
            if not album and 'release-list' in rec and rec['release-list']:
                tags['album'] = rec['release-list'][0]['title']
    except Exception:
        pass
    return tags

