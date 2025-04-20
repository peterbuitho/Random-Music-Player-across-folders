# Gradio-based Music Player (browser UI)
# Ported from tkinter version
import os
import random
import time
import gradio as gr
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
import requests
import re

# --- OpenRouter Chat integration ---
try:
    from openrouter_utils import (
        save_api_key, load_api_key, parse_genre_request, 
        get_available_models, load_selected_model, save_selected_model,
        FREE_MODELS
    )
except ImportError:
    print("OpenRouter utilities not found. Chat features will be disabled.")
    save_api_key = load_api_key = parse_genre_request = None
    get_available_models = load_selected_model = save_selected_model = None
    FREE_MODELS = []

# --- Hybrid API (FastAPI) integration ---
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import mimetypes

# --- End Hybrid API imports ---

# Helper to get all audio files recursively
def get_audio_files(folders, exts=(".mp3", ".flac")):
    files = []
    for folder in folders:
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                if f.lower().endswith(exts):
                    files.append(os.path.join(root, f))
    return files

def get_tags(filepath):
    try:
        audio = File(filepath)
    except Exception as e:
        # print(f"Error reading file: {e}")
        return {'genres': []}
    tags = {}
    if audio is None or not hasattr(audio, 'tags') or audio.tags is None:
        tags['genres'] = []
        return tags
    all_keys = list(audio.tags.keys()) if hasattr(audio.tags, 'keys') else []
    genres = []
    # Look for 'genre', 'GENRE', and 'TCON' (case-insensitive)
    for key in all_keys:
        if key.lower() in ('genre', 'tcon'):
            val = audio.tags[key]
            # Handle both list and string
            if isinstance(val, list):
                for v in val:
                    genres.extend([g.strip() for g in re.split(r'[;|,/\\>\-]+', str(v)) if g.strip()])
            else:
                genres.extend([g.strip() for g in re.split(r'[;|,/\\>\-]+', str(val)) if g.strip()])
    tags['genres'] = genres
    if genres:
        tags['genre'] = genres[0]
    # Get other tags
    for tag in ["title", "artist", "album", "lyrics", "lyric"]:
        for key in all_keys:
            if key.lower() == tag:
                v = audio.tags[key]
                tags[tag] = str(v[0]) if isinstance(v, list) else str(v)
    tags['cover'] = None  # Skipping cover art for now

    # Add duration and year metadata
    try:
        if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
            tags['duration'] = int(audio.info.length)
        for key in all_keys:
            if key.lower() in ('date', 'year'):
                val = audio.tags[key]
                year_str = val[0] if isinstance(val, list) else val
                try:
                    # Try to extract a valid year from the string
                    year_value = int(str(year_str)[:4])
                    # Only use years that make sense (roughly 1900-2100)
                    if 1900 <= year_value <= 2100:
                        tags['year'] = year_value
                except (ValueError, TypeError):
                    # If we can't parse the year, don't set it
                    pass
                break
                
    except Exception:
        pass

    return tags

LYRICS_API = "https://api.lyrics.ovh/v1/{artist}/{title}"
def fetch_lyrics(artist, title):
    max_retries = 2
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            url = LYRICS_API.format(artist=artist, title=title)
            # Add timeout to prevent hanging connections
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get('lyrics', '')
            elif resp.status_code >= 400:
                # Don't retry for client/server errors
                break
                
        except requests.exceptions.ConnectionError:
            # Handle connection reset errors
            if attempt < max_retries - 1:
                # Wait before retrying
                time.sleep(retry_delay)
                continue
        except requests.exceptions.Timeout:
            # Handle timeouts
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
        except Exception:
            # Handle any other exceptions
            break
    
    return ""  # Return empty string if all attempts fail

# --- Gradio App Logic ---

AUDIO_EXTS = (".mp3", ".flac")

# Auto-populate playlist on startup if possible
import threading

def auto_populate_playlist():
    try:
        if hasattr(player, 'playlist') and hasattr(player, 'audio_files'):
            if not player.playlist and player.audio_files:
                n = load_pick_count() if 'load_pick_count' in globals() else 10
                print(f"[Startup] Auto-populating playlist with {n} songs...")
                pick_songs(n, genres=None, should_autoplay=False)
                print(f"[Startup] Playlist populated with {len(player.playlist)} songs.")
            else:
                print(f"[Startup] Playlist already exists or no audio files found. Skipping auto-populate.")
        else:
            print("[Startup] Player not initialized correctly. Cannot auto-populate playlist.")
    except Exception as e:
        print(f"[Startup] Error during auto-populate playlist: {e}")

threading.Timer(0.5, auto_populate_playlist).start()

def pick_songs(n, genres=None, should_autoplay=False):
    """Pick random songs from the library with optional genre filtering.
    Optimized version to prevent CPU spikes and browser hanging.
    """
    import random
    
    # Validate input count
    try:
        n = max(1, min(int(n), 100))  # Limit to reasonable range (1-100)
    except (ValueError, TypeError):
        n = 10  # Default
    
    # Set autoplay flag if requested - do this early in case of any failures
    if should_autoplay:
        player.autoplay_next = True
    
    # Handle empty library case gracefully
    if not player.audio_files:
        player.playlist = []
        player.current = 0
        return {
            "playlist": [],
            "autoplay": player.autoplay_next,
            "current": 0
        }
    
    # Filter by genre more efficiently
    filtered = []
    
    # Only filter if we have genres specified
    if genres and isinstance(genres, (list, tuple)) and len(genres) > 0:
        # Skip empty genre lists
        genres = [g for g in genres if g]  # Remove empty entries
        
        if genres:  # Still have genres after filtering empty ones
            # Use a more efficient approach - convert genres to a set for O(1) lookups
            genre_set = set(genres)
            
            # Pre-compute which files match to avoid nested loops
            for f in player.audio_files:
                file_genres = player.tags_cache.get(f, {}).get('genres', [])
                if any(g in genre_set for g in file_genres):
                    filtered.append(f)
        else:
            # No valid genres, use all files
            filtered = player.audio_files.copy()
    else:
        # No genres specified, use all files
        filtered = player.audio_files.copy()
    
    # Use all available if we have fewer songs than requested
    if len(filtered) <= n:
        player.playlist = filtered.copy()
    else:
        # Take a random sample (more efficient than shuffling the whole list)
        player.playlist = random.sample(filtered, n)
    
    # Reset current position
    player.current = 0
    
    # Return table along with metadata
    playlist_table = player.get_playlist_table()
    
    # Return results with minimal data processing
    return {
        "playlist": playlist_table,
        "autoplay": player.autoplay_next,
        "current": player.current
    }

# Helper: pick songs to match target duration (minutes) with optional genre and year filters
def pick_songs_by_duration(target_minutes, genres=None, year_start=None, year_end=None, title_keywords=None, album_filters=None):
    import random
    player.autoplay_next = True
    pool = []
    for f in player.audio_files:
        tags = player.tags_cache.get(f, {})
        # Genre filter
        if genres and not any(g in tags.get('genres', []) for g in genres):
            continue
        # Title keywords
        if title_keywords:
            title = tags.get('title','').lower()
            if not any(kw.lower() in title for kw in title_keywords):
                continue
        # Album filters
        if album_filters:
            album = tags.get('album','').lower()
            if not any(af.lower() in album for af in album_filters):
                continue
        if year_start and tags.get('year') and tags['year'] < year_start:
            continue
        if year_end and tags.get('year') and tags['year'] > year_end:
            continue
        pool.append(f)
    random.shuffle(pool)
    target_sec = target_minutes * 60
    total = 0
    playlist = []
    for f in pool:
        dur = player.tags_cache.get(f, {}).get('duration', 0)
        if playlist and total + dur > target_sec:
            break
        playlist.append(f)
        total += dur
    player.playlist = playlist
    player.current = 0

# New helper: pick N songs using advanced filters
def pick_songs_by_filters(n, genres=None, title_keywords=None, album_filters=None, year_start=None, year_end=None, artist_filters=None):
    import random
    from rapidfuzz.fuzz import ratio
    FUZZY_THRESHOLD = 80
    # Validate and cap song count
    try:
        n = max(1, min(int(n), 100))
    except (ValueError, TypeError):
        n = load_pick_count()
    player.autoplay_next = True
    pool = []

    
    pool = []
    for f in player.audio_files:
        tags = player.tags_cache.get(f, {})

        # Genre
        if genres and not any(g in tags.get('genres', []) for g in genres):
            continue
        # Title keywords
        if title_keywords:
            title = tags.get('title', '').lower()
            if not any(ratio(kw.lower(), title) >= FUZZY_THRESHOLD for kw in title_keywords):
                continue
        # Album filters
        if album_filters:
            album = tags.get('album', '').lower()
            if not any(ratio(a.lower(), album) >= FUZZY_THRESHOLD for a in album_filters):
                continue
        # Artist filters
        if artist_filters:
            artist = tags.get('artist', '').lower()
            if not any(ratio(a.lower(), artist) >= FUZZY_THRESHOLD for a in artist_filters):
                continue
        # Year range
        if year_start and tags.get('year') and tags['year'] < year_start:
            continue
        if year_end and tags.get('year') and tags['year'] > year_end:
            continue
        pool.append(f)
    
    if not pool:
        player.playlist = []
        player.current = 0
        return
    if len(pool) <= n:
        playlist = pool.copy()
    else:
        playlist = random.sample(pool, n)
    player.playlist = playlist
    player.current = 0

class MusicPlayerGradio:
    def __init__(self):
        self.folders = []
        self.audio_files = []
        self.playlist = []
        self.current = 0
        self.genres = set()
        self.genre_filter = set()
        self.tags_cache = {}
        self.scanning = False
        self.autoplay_next = False  # Flag to indicate if next playlist load should autoplay

    def scan_files(self, folders):
        self.folders = folders
        self.audio_files = get_audio_files(folders, AUDIO_EXTS)
        self.tags_cache = {}
        genre_set = set()

        for i, f in enumerate(self.audio_files):
            tags = get_tags(f)
            # Fetch missing metadata if needed
            if not tags.get('year') or not tags.get('artist') or not tags.get('album') or not tags.get('title'):

                tags = get_tags(f)  # Re-read after update
            self.tags_cache[f] = tags
            genre_set.update(tags.get('genres', []))
            if i < 3:
                if hasattr(File(f), 'tags') and File(f).tags:
                    for k in File(f).tags.keys():
                        pass
                else:
                    pass
            self.genres = genre_set
            self.genre_filter = set()
            self.playlist = self.audio_files.copy()
        random.shuffle(self.playlist)
        self.current = 0
        print(f"[DEBUG] scan_files: Playlist populated with {len(self.playlist)} songs.")
        # Always return the genre list, even if empty
        return self.get_playlist_table(), sorted(list(self.genres))

    def filter_by_genre(self, genres):
        # print(f"Filtering by genres: {genres}")
        if genres is None:
            genres = []
        self.genre_filter = set(genres)
        if not genres:
            self.playlist = self.audio_files.copy()
        else:
            self.playlist = [f for f in self.audio_files if any(g in self.tags_cache.get(f, {}).get('genres', []) for g in genres)]
        random.shuffle(self.playlist)
        self.current = 0
        return self.get_playlist_table()

    def get_playlist_table(self):
        rows = []
        for idx, f in enumerate(self.playlist): tags = self.tags_cache.get(f) or get_tags(f)
        # Make sure we have at least a title
        title = tags.get('title')
        if not title or title.strip() == '':
            title = os.path.basename(f)
        artist = tags.get('artist', '')
        album = tags.get('album', '')
        # Fix empty or zero years
        year = tags.get('year', '')
        if year == 0 or not str(year).strip():
            year = ''
        genres = ', '.join(tags.get('genres', []))
        # Only add rows with valid titles
        if title and title.strip() != '':
            rows.append([idx+1, title, artist, album, year, genres])
        return rows

    def get_current_audio(self):
        if not self.playlist:
            return None, None, None
        f = self.playlist[self.current]
        tags = self.tags_cache.get(f) or get_tags(f)
        title = tags.get('title', os.path.basename(f))
        artist = tags.get('artist', '')
        audio_url = f
        return audio_url, title, artist

    def play(self):
        audio_url, title, artist = self.get_current_audio()
        if audio_url is None:
            # Playlist is empty or invalid
            return None, "No song loaded", "", "No songs found in playlist. Please scan folders or check your music directory."
        lyrics = fetch_lyrics(artist, title) if artist and title else ""
        return audio_url, title, artist, lyrics

    def next(self):
        if not self.playlist:
            return None, "No song loaded", "", "No songs found in playlist. Please scan folders or check your music directory."
        if self.current < len(self.playlist) - 1:
            self.current += 1
        return self.play()

    def prev(self):
        if not self.playlist:
            return None, "No song loaded", "", "No songs found in playlist. Please scan folders or check your music directory."
        if self.current > 0:
            self.current -= 1
        return self.play()

player = MusicPlayerGradio()

def parse_folder_input(folder_input):
    if not folder_input:
        return []
    # Split on comma or semicolon
    paths = [p.strip() for p in re.split(r'[;,]', folder_input) if p.strip()]
    # Optionally, filter to only existing directories
    paths = [p for p in paths if os.path.isdir(p)]
    return paths

import threading
import time
import json
import os

CACHE_DIR = "cache"
CACHE_FILE = os.path.join(CACHE_DIR, "scan_cache.json")

def save_scan_cache(folders, audio_files, tags_cache, genres, folder_input_value=None):
    try:
        if not os.path.isdir(CACHE_DIR):
            os.makedirs(CACHE_DIR, exist_ok=True)
        cache = {
            "folders": folders,
            "audio_files": audio_files,
            "tags_cache": tags_cache,
            "genres": list(genres)
        }
        if folder_input_value is not None:
            cache["folder_input_value"] = folder_input_value
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"[WARNING] Could not save scan cache: {e}")

def load_scan_cache():
    if not os.path.isfile(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return cache
    except Exception as e:
        print(f"[WARNING] Could not load scan cache: {e}")
        return None

def background_scan(folders):
    audio_files = get_audio_files(folders, AUDIO_EXTS)
    genres = set()
    player.audio_files = []
    player.tags_cache = {}
    player.scanning = True
    for i, f in enumerate(audio_files):
        if not player.scanning:
            break
        tags = get_tags(f)
        player.audio_files.append(f)
        player.tags_cache[f] = tags
        genres.update(tags.get('genres', []))
        player.genres = genres
    player.genre_filter = set()
    player.playlist = player.audio_files.copy()
    player.current = 0
    player.scanning = False
    # Save scan to cache
    # Save scan to cache, including the folder input value
    save_scan_cache(folders, player.audio_files, player.tags_cache, player.genres, getattr(player, 'last_folder_input', None))

def start_background_scan(folder_input):
    folders = parse_folder_input(folder_input)
    player.last_folder_input = folder_input
    # Stop any previous scan
    if hasattr(player, 'scanning') and player.scanning:
        player.scanning = False
        time.sleep(0.1)
    # Check cache
    cache = load_scan_cache()
    if cache and cache.get("folders") == folders:
        # Load from cache
        player.audio_files = cache["audio_files"]
        player.tags_cache = cache["tags_cache"]
        player.genres = set(cache["genres"])
        player.genre_filter = set()
        player.playlist = player.audio_files.copy()
        player.current = 0
        player.scanning = False
        # Also remember last folder input
        player.last_folder_input = cache.get("folder_input_value", folder_input)
        status = f"Loaded {len(player.audio_files)} songs from cache."
        return status, gr.update(choices=sorted(list(player.genres)), value=[]), status
    # Otherwise, scan in background
    scan_thread = threading.Thread(target=background_scan, args=(folders,), daemon=True)
    scan_thread.start()
    status = "Scanning in background... (click Refresh to update)"
    return status, gr.update(choices=[]), status

def refresh_playlist_and_genres():
    # Only update the UI with the current scan progress; do NOT start a new scan or touch the cache
    genres = set()
    for f in player.audio_files:
        tags = player.tags_cache.get(f) or get_tags(f)
        genres.update(tags.get('genres', []))
    player.genres = genres
    status = f"Songs found so far: {len(player.audio_files)} (refresh only, scan may still be running)"
    return status, gr.update(choices=sorted(list(player.genres)), value=[]), status

def clear_cache():
    try:
        if os.path.isfile(CACHE_FILE):
            os.remove(CACHE_FILE)
            return "Cache cleared. Please scan folders again.", gr.update(choices=[]), "Cache cleared."
        else:
            return "No cache to clear.", gr.update(choices=[]), "No cache to clear."
    except Exception as e:
        return f"Error clearing cache: {e}", gr.update(choices=[]), f"Error clearing cache: {e}"

def update_genre_filter(selected_genres):
    # Only update the song count, not the playlist table, after filtering by genre
    total = len(player.filter_by_genre(selected_genres)) if selected_genres else len(player.audio_files)
    return f"Total songs found: {total}"

def play(selected_index=None):
    if selected_index is not None and selected_index != "":
        idx = int(selected_index) - 1
        if 0 <= idx < len(player.playlist):
            player.current = idx
    return player.play()

def next_song():
    return player.next()

def prev_song():
    return player.prev()

import sys
import gradio
print("Gradio version in use:", gradio.__version__)
print("Gradio location:", gradio.__file__)
import gradio.themes

# --- Set allowed_paths for Gradio launch (static at startup) ---
def get_allowed_paths():
    paths = [os.getcwd()]
    # Allow all subfolders under C:, D:, and network share \\BuiDS\musik
    broad_allowed = [
        'C:\\',
        'D:\\',
        '\\BuiDS\\musik',
        '//BuiDS/musik',
        '/volume1/musik/24bit_flac',
        '/volume1/musik/16bit',
    ]
    paths.extend(broad_allowed)
    return paths

# --- Theme settings ---
import gradio.themes
import json as _json
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
def load_theme():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = _json.load(f)
        return settings.get("theme", "Soft")
    except Exception:
        return "Soft"
def save_theme(theme_name):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump({"theme": theme_name}, f)
    except Exception as e:
        print(f"[WARNING] Could not save theme: {e}")

THEME_MAP = {
    "Default": None,
    "Soft": gr.themes.Soft(),
    "Monochrome": gr.themes.Monochrome()
}
_selected_theme = load_theme()
def load_pick_count():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = _json.load(f)
        return int(settings.get("pick_count", 10))
    except Exception:
        return 10

def save_pick_count(n):
    try:
        # Load current settings
        settings = {}
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = _json.load(f)
        settings["pick_count"] = int(n)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump(settings, f)
    except Exception as e:
        print(f"[WARNING] Could not save pick_count: {e}")
    return n

pick_count = gr.Number(value=load_pick_count(), label="Number of Songs to Pick", precision=0)
with gr.Blocks(theme=THEME_MAP.get(_selected_theme, gr.themes.Soft()), css="""
/* Make the play button green and pause button red in the audio player */
audio::-webkit-media-controls-play-button {
    background-color: #27ae60 !important; /* green */
    border-radius: 50%;
}
audio:paused::-webkit-media-controls-play-button {
    background-color: #e74c3c !important; /* red when paused */
}
audio:-webkit-media-controls-play-button {
    color: white !important;
}

/* Compact action buttons */
.small-btn button {
    min-width: 70px !important;
    max-width: 100px !important;
    width: auto !important;
    padding: 0.1em 0.7em !important;
    font-size: 0.9em !important;
}
""") as demo:
    gr.Markdown("# Random Music Player (Gradio)")
    with gr.Tabs():
        # --- New WaveSurfer Player tab ---
        with gr.Tab("Player"):
            # Embed the custom player as an iframe for full JS/CSS isolation
            gr.HTML('<iframe id="wavesurfer-iframe" src="/static/player.html" style="width:100%;height:auto;min-height:1200px;max-height:95vh;border:none;max-width:100%;margin:auto;display:block;"></iframe>')
            gr.HTML('''<script>
(function() {
    function sendThemeToIframe() {
        var theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
        var iframe = document.getElementById('wavesurfer-iframe');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({type: 'set-theme', theme: theme}, '*');
        }
    }
    // Send on load
    window.addEventListener('DOMContentLoaded', sendThemeToIframe);
    // Send on theme change (Gradio toggles .dark on <html>)
    const observer = new MutationObserver(sendThemeToIframe);
    observer.observe(document.documentElement, {attributes: true, attributeFilter: ['class']});
    // Also send after a short delay in case iframe loads late
    setTimeout(sendThemeToIframe, 1000);
})();
</script>''')

        # --- Renamed tab ---
        with gr.Tab("Create playlist"):
            gr.Markdown(r"""
**Tip:** You can enter multiple music folder paths, separated by commas or semicolons.<br>
**Example:**
```
\\<server>\music; /<volume>/music
```
(You can use either forward or backslashes for paths.)
""")
            # Load folder input value and scan data from cache if available
            _folder_input_value = None
            _cache = None
            try:
                _cache = load_scan_cache()
                if _cache and _cache.get("folder_input_value"):
                    _folder_input_value = _cache["folder_input_value"]
            except Exception:
                _folder_input_value = None
            folder_input = gr.Textbox(
                label="Music Folder Paths",
                placeholder=r"e.g. D:/Music1, D:/Music2; \\BuiDS\musik",
                value=_folder_input_value or ""
            )
            # Restore scan data to player if cache matches folder input
            if _cache and _folder_input_value is not None:
                cached_folders = _cache.get("folders")
                input_folders = parse_folder_input(_folder_input_value)
                if cached_folders == input_folders:
                    player.audio_files = _cache.get("audio_files", [])
                    player.tags_cache = _cache.get("tags_cache", {})
                    player.genres = set(_cache.get("genres", []))
                    player.genre_filter = set()
                    player.playlist = player.audio_files.copy()
                    player.current = 0
                    player.scanning = False
            with gr.Row():
                scan_btn = gr.Button("Scan Folders", elem_classes="small-btn")
                refresh_btn = gr.Button("Refresh Playlist / Genres", elem_classes="small-btn")
                clear_cache_btn = gr.Button("Clear Cache", elem_classes="small-btn")
            status_text = gr.Textbox(label="Status", interactive=False, value="", visible=True)

            # Collapsible genre filter section
            with gr.Accordion("📋 Genre Filters (click to expand)", open=False):
                genre_choices = sorted(list(player.genres)) if getattr(player, 'genres', None) else []
                genre_dropdown = gr.CheckboxGroup(choices=genre_choices, label="Filter by Genre", interactive=True)
                update_genre_btn = gr.Button("Apply Genre Filter", elem_classes="small-btn")
            
            with gr.Row():
                pick_songs_btn = gr.Button("Pick songs", elem_classes="small-btn")

            # Set initial song count if scan data is restored
            _song_count_value = f"Total songs found: {len(player.audio_files)}" if getattr(player, 'audio_files', None) else ""
            song_count_text = gr.Textbox(label="Song Count", interactive=False, value=_song_count_value)
            playlist_table = gr.Dataframe(headers=["#", "Title", "Artist", "Album", "Genres"], interactive=False, label="Playlist")

            # --- Hide audio player, transport, title, artist, lyrics in Music Library tab ---
            # Only show playlist table and controls

            # --- Update song selector choices after scanning or picking songs ---
            def update_song_choices():
                table = player.get_playlist_table()
                choices = [str(i+1) for i in range(len(player.playlist))]
                return gr.update(choices=choices, value=choices[0] if choices else ""), table
            scan_btn.click(
                fn=start_background_scan,
                inputs=[folder_input],
                outputs=[song_count_text, genre_dropdown, status_text]
            )
            refresh_btn.click(
                fn=refresh_playlist_and_genres,
                outputs=[song_count_text, genre_dropdown, status_text]
            )
            clear_cache_btn.click(
                fn=clear_cache,
                outputs=[song_count_text, genre_dropdown, status_text]
            )
            update_genre_btn.click(
                fn=lambda genres: f"Total songs found: {len(player.filter_by_genre(genres))}",
                inputs=[genre_dropdown],
                outputs=[song_count_text]
            )
            # Connect the Pick songs button - simple pre-LLM style
            def pick_and_update_table(n, genres):
                # Simple function like before LLM integration
                try:
                    n = max(1, min(int(n), 100))
                except (ValueError, TypeError):
                    n = load_pick_count()
                
                # Set autoplay flag
                player.autoplay_next = True
                
                # Simple filtering and playlist update
                if genres:
                    filtered = [f for f in player.audio_files if any(g in player.tags_cache.get(f, {}).get('genres', []) for g in genres)]
                else:
                    filtered = player.audio_files.copy()
                
                # Update playlist
                if len(filtered) <= n:
                    player.playlist = filtered.copy()
                else:
                    import random
                    player.playlist = random.sample(filtered, n)
                
                player.current = 0
                
                # Use enhanced direct approach to refresh the player with better parameters
                js_code = '''
                <script>
                setTimeout(function() {
                    console.log("Triggering player refresh from manual pick...");
                    // Direct reload approach with enhanced parameters
                    var refreshFrame = document.createElement('iframe');
                    refreshFrame.style.display = 'none';
                    refreshFrame.src = '/direct-refresh-playlist?autoplay=true&api=gradio&ts=' + Date.now();
                    document.body.appendChild(refreshFrame);
                    
                    // Remove the frame after it's loaded to clean up
                    refreshFrame.onload = function() {
                        console.log("Player refresh request completed");
                        setTimeout(function() {
                            document.body.removeChild(refreshFrame);
                        }, 1000);
                    };
                }, 300); // Reduced delay for faster response
                </script>
                '''
                
                # Return new playlist table and refresh script
                return player.get_playlist_table(), gr.update(value=js_code)
            
            autoplay_script = gr.HTML(visible=True)
            
            pick_songs_btn.click(
                fn=pick_and_update_table,
                inputs=[pick_count, genre_dropdown],
                outputs=[playlist_table, autoplay_script]
            )

        # Chat interface tab
        with gr.Tab("Chat"):
            gr.Markdown("### Chat with AI to control your music player")
            chat_history = gr.Chatbot(height=400, label="Chat History", type="messages")
            
            with gr.Row():
                chat_input = gr.Textbox(label="Ask the AI to pick songs or filter by genre", placeholder="Example: Play 5 random rock songs", lines=2)
            chat_submit = gr.Button("Send", variant="primary")
            # Custom JS: Ctrl+Enter submits, Enter inserts newline
            gr.HTML("""
            <script>
            (function() {
                let chatBox = document.querySelector('textarea[placeholder*="pick songs"], textarea[placeholder*="LLM"]');
                if (chatBox) {
                    chatBox.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter' && e.ctrlKey) {
                            e.preventDefault();
                            // Find the Send button and click it
                            let sendBtn = chatBox.parentElement.parentElement.querySelector('button');
                            if (sendBtn) sendBtn.click();
                        }
                        // Enter alone inserts newline (default behavior)
                    });
                }
            })();
            </script>
            """)
            
            with gr.Row():
                chat_status = gr.Markdown("")
            
            def chat_and_pick_songs(message, history):
                # Check if OpenRouter integration is available
                if parse_genre_request is None:
                    return history + [{"role": "assistant", "content": "OpenRouter integration is not available. Please make sure openrouter_utils.py is in the same directory."}], "", None
                
                # Check if API key is set
                api_key = load_api_key()
                if not api_key:
                    return history + [{"role": "assistant", "content": "No API key found. Please add your OpenRouter API key in settings."}], "", None
                
                # Get available genres
                available_genres = sorted(list(player.genres)) if player.genres else []
                if not available_genres:
                    return history + [{"role": "assistant", "content": "No genres found. Please scan your music folders first."}], "", None
                
                # Add user prompt to history
                new_history = history + [{"role": "user", "content": message}]
                
                try:
                    # Parse the request for genres, count or duration, and year range
                    selected_genres, num_songs, duration, year_start, year_end, title_keywords, album_filters, artist_filters, error = parse_genre_request(message, available_genres)
                    
                    if error:
                        # Add assistant error response to history
                        new_history.append({"role": "assistant", "content": f"Error: {error}"})
                        return new_history, "", None
                    
                    # Ensure at least a count or duration
                    if duration is None and num_songs is None:
                        num_songs = load_pick_count()
                    
                    # Pick by duration if specified, otherwise by count
                    if duration:
                        pick_songs_by_duration(duration, selected_genres, year_start, year_end, title_keywords, album_filters)
                        # Build optional year text
                        yr_text = ""
                        if year_start and year_end:
                            yr_text = f" between {year_start} and {year_end}"
                        elif year_start:
                            yr_text = f" from {year_start} onward"
                        elif year_end:
                            yr_text = f" up to {year_end}"
                        response = f"Playing ~{duration} minutes of {', '.join(selected_genres)} songs{yr_text}. The music will start momentarily."
                        # Check if any songs were picked
                        if not player.playlist:
                            response = "No songs matched your filters. Please try different criteria."
                    else:
                        pick_songs_by_filters(num_songs, selected_genres, title_keywords, album_filters, year_start, year_end, artist_filters)
                        
                        # Set autoplay only if songs were picked
                        if player.playlist:
                            player.autoplay_next = True
                        # Add year/decade info to response if present
                        yr_text = ""
                        if year_start and year_end:
                            yr_text = f" between {year_start} and {year_end}"
                        elif year_start:
                            yr_text = f" from {year_start} onward"
                        elif year_end:
                            yr_text = f" up to {year_end}"
                        filter_parts = []
                        if selected_genres:
                            filter_parts.append(f"genres: {', '.join(selected_genres)}")
                        if title_keywords:
                            filter_parts.append(f"titles: {', '.join(title_keywords)}")
                        if album_filters:
                            filter_parts.append(f"albums: {', '.join(album_filters)}")
                        if artist_filters:
                            filter_parts.append(f"artists: {', '.join(artist_filters)}")
                        if yr_text:
                            filter_parts.append(yr_text.strip())
                        filter_summary = "; ".join(filter_parts)
                        response = f"Playing {num_songs} songs from filters: {filter_summary}. The music will start momentarily."
                        # Check if any songs were picked
                        if not player.playlist:
                            response = "No songs matched your filters. Please try different criteria."
                    # Add assistant answer to chat history
                    new_history.append({"role": "assistant", "content": response})
                    # Use enhanced direct approach to refresh the player with better parameters
                    js_code = '''
                    <script>
                    setTimeout(function() {
                        console.log("Triggering player refresh from LLM request...");
                        // Direct reload approach with enhanced parameters
                        var refreshFrame = document.createElement('iframe');
                        refreshFrame.style.display = 'none';
                        refreshFrame.src = '/direct-refresh-playlist?autoplay=true&api=llm&ts=' + Date.now();
                        document.body.appendChild(refreshFrame);
                        
                        // Remove the frame after it's loaded to clean up
                        refreshFrame.onload = function() {
                            console.log("Player refresh request from LLM completed");
                            setTimeout(function() {
                                document.body.removeChild(refreshFrame);
                            }, 1000);
                        };
                    }, 300); // Reduced delay for faster response
                    </script>
                    '''
                    
                    return new_history, "", gr.update(value=js_code)
                    
                except Exception as e:
                    new_history.append({"role": "assistant", "content": f"An error occurred: {str(e)}"})
                    return new_history, "", None
            
            chat_submit.click(
                fn=chat_and_pick_songs,
                inputs=[chat_input, chat_history],
                outputs=[chat_history, chat_input, autoplay_script]
            )
            chat_input.submit(
                fn=chat_and_pick_songs,
                inputs=[chat_input, chat_history],
                outputs=[chat_history, chat_input, autoplay_script]
            )
            
            gr.Markdown("""
            ### Example phrases:
            - "Play 5 random jazz songs"  
            - "I want to listen to some rock and metal music"  
            - "Create a playlist with 15 classical and ambient songs"  
            - "Pick some electronic tracks"  
            """)
            
        with gr.Tab("Settings"):
            gr.Markdown("### General Settings")
            with gr.Row():
                pick_count.render()
            pick_count.change(fn=save_pick_count, inputs=[pick_count], outputs=[pick_count])
            gr.Markdown("Set how many random songs to pick when you use the 'Pick songs' button in the Player tab.")
            
            # OpenRouter API key settings
            gr.Markdown("### AI Chat Settings")
            openrouter_api_key = gr.Textbox(
                label="OpenRouter API Key", 
                placeholder="Enter your OpenRouter API key",
                type="password",
                value=load_api_key() or ""
            )
            
            save_key_btn = gr.Button("Save API Key")
            key_status = gr.Markdown("")
            
            # Model selection
            gr.Markdown("#### Select LLM Model")
            gr.Markdown("Choose which AI model to use for chat. OpenRouter provides various models, including free options.")
            
            # Function to fetch and format models from OpenRouter
            def fetch_models(free_only=False):
                available_models = get_available_models(include_free_only=free_only) if get_available_models else FREE_MODELS
                
                # Format for dropdown
                model_choices = []
                model_desc_dict = {}
                pricing_info = {}
                
                for model in available_models:
                    model_id = model["id"]
                    name = model.get("name", model_id)
                    desc = model.get("description", "")
                    latency = model.get("latency", 999)
                    
                    # Add speed indicators to model names based on latency
                    speed_indicator = ""
                    if latency < 1.5:
                        speed_indicator = "⚡ "  # Fast
                    elif latency < 2.5:
                        speed_indicator = "✓ "   # Medium
                    elif latency < 3.5:
                        speed_indicator = "🕒 "  # Slower
                    else:
                        speed_indicator = "⏱️ "  # Very slow
                    
                    display_name = f"{speed_indicator}{name}"  # Add speed indicator to displayed name
                    
                    # Format pricing information if available
                    price_info = ""
                    pricing = model.get("pricing", {})
                    if pricing:
                        input_price = pricing.get("prompt", 0)
                        output_price = pricing.get("completion", 0)
                        if input_price or output_price:
                            price_info = f"Pricing: ${input_price}/1M tokens (input), ${output_price}/1M tokens (output)"
                    
                    # Add latency info to the description
                    latency_info = ""
                    if latency < 999:  # If we have a valid latency estimate
                        # Convert numeric latency to human-readable description
                        if latency < 1.5:
                            speed = "Very fast response time"
                        elif latency < 2.5:
                            speed = "Medium response time"
                        elif latency < 3.5:
                            speed = "Slower response time"
                        else:
                            speed = "Slow response time"
                        latency_info = f"**Speed**: {speed}"  # Bold for emphasis
                    
                    model_choices.append((display_name, model_id))
                    model_desc_dict[model_id] = desc
                    pricing_info[model_id] = price_info + ("\n\n" + latency_info if latency_info else "")
                
                return model_choices, model_desc_dict, pricing_info
            
            # Get current model from config
            current_model = load_selected_model() if load_selected_model else DEFAULT_MODEL
            print(f"Loading model selection UI with model: {current_model}")
            
            # Get initial models
            initial_free_only = False  # Start with all models
            model_choices, model_descs, pricing_info = fetch_models(initial_free_only)
            
            # Make sure the current model is in the list - if not, add it
            found_in_list = False
            for _, model_id in model_choices:
                if model_id == current_model:
                    found_in_list = True
                    break
            
            # If current model isn't in the list (e.g., it's a premium model but we're showing free only),
            # add it to the choices to ensure it's selectable
            if not found_in_list and current_model:
                # Add the current model to the beginning of the list
                model_choices.insert(0, (f"Current: {current_model}", current_model))
                if current_model not in model_descs:
                    model_descs[current_model] = "Your currently selected model"
            
            # Default to the saved model or first available
            default_model_idx = 0
            if current_model and model_choices:
                for i, (name, model_id) in enumerate(model_choices):
                    if model_id == current_model:
                        default_model_idx = i
                        break
                print(f"Setting dropdown to index {default_model_idx} for model {current_model}")
            
            # Free models toggle
            with gr.Row():
                free_only_checkbox = gr.Checkbox(
                    label="Show only free/included models", 
                    value=initial_free_only,
                    info="Filters models to show only those marked as free or included in the API"
                )
                refresh_models_btn = gr.Button("Refresh Models")
            
            # Models dropdown
            with gr.Row():
                model_dropdown = gr.Dropdown(
                    choices=model_choices,
                    value=model_choices[default_model_idx][1] if model_choices and len(model_choices) > default_model_idx else None,
                    label="AI Model",
                    interactive=True
                )
            
            # Model description
            model_description = gr.Markdown(
                model_descs.get(current_model, "") + 
                ("\n\n" + pricing_info.get(current_model, "") if current_model in pricing_info and pricing_info[current_model] else "")
            )
            
            # Function to refresh model list
            def refresh_model_list(free_only):
                model_choices, model_descs, pricing_info = fetch_models(free_only)
                return gr.Dropdown(choices=model_choices), ""
            
            # Function to update model description
            def update_model_description(model_id):
                desc = model_descs.get(model_id, "")
                pricing = pricing_info.get(model_id, "")
                if pricing:
                    desc = desc + "\n\n" + pricing
                return desc
            
            def save_model_and_show_status(model_id):
                if not model_id:
                    return "Please select a model"
                
                try:
                    save_selected_model(model_id)
                    return f"✅ Model set to {model_id}"
                except Exception as e:
                    return f"Error saving model choice: {str(e)}"
            
            # Connect model dropdown to description
            model_dropdown.change(
                fn=update_model_description,
                inputs=[model_dropdown],
                outputs=[model_description]
            )
            
            # Connect free model toggle and refresh button
            free_only_checkbox.change(
                fn=refresh_model_list,
                inputs=[free_only_checkbox],
                outputs=[model_dropdown, model_description]
            )
            
            refresh_models_btn.click(
                fn=refresh_model_list,
                inputs=[free_only_checkbox],
                outputs=[model_dropdown, model_description]
            )
            
            # Save model button
            save_model_btn = gr.Button("Save Model Preference")
            model_status = gr.Markdown("")
            
            save_model_btn.click(
                fn=save_model_and_show_status,
                inputs=[model_dropdown],
                outputs=[model_status]
            )
            
            def save_key_and_show_status(api_key):
                if not api_key or len(api_key.strip()) < 10:
                    return "Error: Invalid API key"
                    
                try:
                    save_api_key(api_key.strip())
                    return "✅ API key saved successfully"
                except Exception as e:
                    return f"Error saving API key: {str(e)}"
            
            save_key_btn.click(
                fn=save_key_and_show_status,
                inputs=[openrouter_api_key],
                outputs=[key_status]
            )
            # --- Theme selector UI ---
            def set_theme(new_theme):
                save_theme(new_theme)
                return f"Theme set to {new_theme}. Please reload the app to apply."
            theme_dropdown = gr.Dropdown(["Default", "Soft", "Monochrome"], value=_selected_theme, label="Gradio Theme", interactive=True)
            theme_status = gr.Markdown(visible=False)
            
            # Combine theme handlers into a single function
            def handle_theme_change(theme):
                # Set the theme
                save_theme(theme)
                # Show and update the status message
                return gr.update(value=f"Theme set to {theme}. Please reload the app to apply.", visible=True)
            
            # Connect the single handler
            theme_dropdown.change(fn=handle_theme_change, inputs=[theme_dropdown], outputs=[theme_status])
            # --- Restart server button ---
            import sys
            def restart_server():
                import os
                import time
                # Only allow restart if started as a script
                if not sys.argv or sys.argv[0] == '-c' or not os.path.isfile(sys.argv[0]):
                    return "Automatic restart is not supported for your launch method. Please restart the server manually."
                # Show message before restarting
                time.sleep(0.5)
                os.execl(sys.executable, sys.executable, *sys.argv)

            with gr.Row():
                restart_btn = gr.Button("Restart Server", elem_classes="small-btn")
                stop_btn = gr.Button("Stop Server", elem_classes="small-btn")
            restart_status = gr.Markdown(visible=False)
            def show_restarting():
                return "Restarting server..."
            restart_btn.click(fn=restart_server, outputs=[restart_status])
            restart_btn.click(fn=restart_server, outputs=[])
            restart_btn.click(fn=show_restarting, outputs=[restart_status])
            def stop_server():
                import os
                os._exit(0)
            stop_btn.click(fn=stop_server, outputs=[])


allowed_paths = get_allowed_paths()

# --- Hybrid API (FastAPI) endpoints ---
from fastapi import FastAPI
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import mimetypes
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount /static for player assets (JS, CSS, HTML)
static_dir = os.path.join(os.path.dirname(__file__), 'static')

if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Allow CORS for all origins (for development, restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper to get cover art path (if any)
def get_cover_path(filepath):
    # Look for cover.jpg/png in the same folder, or embedded cover in tags
    folder = os.path.dirname(filepath)
    for name in ["cover.jpg", "cover.png", "folder.jpg", "folder.png"]:
        test_path = os.path.join(folder, name)
        if os.path.isfile(test_path):
            return test_path
    # Embedded cover art: not implemented here (mutagen can extract, but needs more logic)
    return None

# API: /playlist - returns all songs with metadata, lyrics, and cover art URL
@app.get("/playlist")
async def playlist_api(request: Request):
    # Import modules needed within this function
    import time
    import random
    # Check query parameters for any refresh indicators
    params = request.query_params
    force_refresh = params.get('nocache') or params.get('force_refresh') or params.get('ts')
    # Only generate a new playlist if explicitly requested with 'new_playlist'
    generate_new = params.get('new_playlist') == '1' or params.get('new_playlist') == 'true'
    
    # Only generate a new playlist if explicitly requested
    if generate_new:
        print(f"Server received forced playlist refresh with parameter: {force_refresh}")
        
        # Generate truly fresh random playlist
        import random
        import time
        
        # Use a different seed each time
        random_seed = int(time.time() * 1000000) + random.randint(1, 1000000)
        random.seed(random_seed)
        print(f"Using random seed: {random_seed}")
        
        # Get all audio files and randomly select some
        all_files = player.audio_files.copy()
        if all_files:
            random.shuffle(all_files)
            n = min(len(all_files), 10)  # Default to 10 songs
            
            # Get current playlist titles for comparison
            current_titles = []
            if player.playlist:
                for f in player.playlist[:3]:
                    tags = player.tags_cache.get(f, {}) 
                    current_titles.append(tags.get('title', os.path.basename(f)))
            
            # Generate new playlist
            new_playlist = all_files[:n]
            
            # Check if first song is the same, if so, shift the playlist
            if player.playlist and new_playlist and player.playlist[0] == new_playlist[0]:
                print("First song is the same - shifting playlist")
                if len(new_playlist) > 1:
                    new_playlist = new_playlist[1:] + [new_playlist[0]]
            
            # Update player's playlist
            player.playlist = new_playlist
            player.current = 0
            player.autoplay_next = True
            
            # Log what we've picked
            new_titles = []
            for f in player.playlist[:3]:
                tags = player.tags_cache.get(f, {})
                new_titles.append(tags.get('title', os.path.basename(f)))
            
            print(f"Previous first songs: {current_titles}")
            print(f"New first songs: {new_titles}")
    
    # Create playlist data
    playlist = []
    for idx, f in enumerate(player.playlist):
        tags = player.tags_cache.get(f) or get_tags(f)
        title = tags.get('title', os.path.basename(f))
        artist = tags.get('artist', '')
        album = tags.get('album', '')
        year = tags.get('year', '')
        genres = tags.get('genres', [])
        lyrics = tags.get('lyrics', '') or tags.get('lyric', '')
        cover_url = None
        cover_path = get_cover_path(f)
        if cover_path:
            cover_url = f"/cover/{idx}"
        playlist.append({
            "index": idx,
            "title": title,
            "artist": artist,
            "album": album,
            "year": year,
            "genres": genres,
            "audio_url": f"/audio/{idx}?cache={int(time.time() * 1000 + random.randint(1, 10000))}",
            "lyrics_url": f"/lyrics/{idx}",
            "cover_url": cover_url
        })
    
    # Check if we need to autoplay and reset the flag ONLY when it's consumed
    # This ensures the autoplay flag persists until the client actually uses it
    autoplay = player.autoplay_next
    
    # Add the current index to help the player know which song to play
    current_idx = player.current
    
    # Get the autoplay state and create a unique signature for this playlist
    # This helps the frontend track if this is a genuinely new playlist or just a refresh
    playlist_signature = "-".join(str(item["title"]) for item in playlist[:5])
    
    # Only reset the autoplay flag if we're actually sending it as true
    # This way if the frontend fails to get the signal, we'll keep trying
    if autoplay:
        # Log that we're sending an autoplay command
        print(f"Sending autoplay command to frontend for playlist: {playlist_signature[:30]}...")
    
    # Return playlist with additional metadata
    response = {
        "playlist": playlist,
        "autoplay": autoplay,
        "current": current_idx,
        "signature": playlist_signature
    }
    
    # Only reset the autoplay flag AFTER creating the response
    if autoplay:
        player.autoplay_next = False  # Reset the flag after sending it
    
    return JSONResponse(response)

# API: /audio/{idx} - serves audio file by playlist index
@app.get("/audio/{idx}")
def audio_file(idx: int):
    try:
        f = player.playlist[idx]
        ext = os.path.splitext(f)[1].lower()
        mime = mimetypes.types_map.get(ext, "audio/mpeg")
        
        # Custom response handling to suppress connection reset errors
        try:
            # Create response with anti-caching headers
            response = FileResponse(f, media_type=mime, filename=os.path.basename(f))
            # Add cache control headers to prevent caching
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            # Add a timestamp to make each response unique
            response.headers["X-Timestamp"] = str(time.time())
            return response
        except ConnectionResetError:
            # Client disconnected, just return a normal response
            # This prevents the error from showing in the logs
            return Response(status_code=200)
        except Exception as e:
            # Log other errors but don't show stack trace
            print(f"Error serving audio file: {str(e)}")
            return Response(status_code=500)
            
    except IndexError:
        # Playlist index out of range
        return Response(status_code=404)
    except Exception as e:
        # Any other exception
        print(f"Unexpected error in audio_file: {str(e)}")
        return Response(status_code=500)

# API: /lyrics/{idx} - returns lyrics for song (try cache, else fetch)
@app.get("/lyrics/{idx}")
def lyrics_api(idx: int):
    try:
        f = player.playlist[idx]
        tags = player.tags_cache.get(f) or get_tags(f)
        artist = tags.get('artist', '')
        title = tags.get('title', os.path.basename(f))
        lyrics = tags.get('lyrics', '') or tags.get('lyric', '')
        if not lyrics and artist and title:
            lyrics = fetch_lyrics(artist, title)
        return JSONResponse({"lyrics": lyrics or ""})
    except Exception:
        return JSONResponse({"lyrics": ""})

# API: /cover/{idx} - serves cover art image if found
@app.get("/cover/{idx}")
def cover_api(idx: int):
    try:
        f = player.playlist[idx]
        cover_path = get_cover_path(f)
        if cover_path:
            ext = os.path.splitext(cover_path)[1].lower()
            mime = mimetypes.types_map.get(ext, "image/jpeg")
            return FileResponse(cover_path, media_type=mime)
    except Exception:
        pass
    return Response(status_code=404)

# API: /pick_songs - pick a new random playlist
from fastapi import Request
@app.post("/pick_songs")
async def pick_songs_api(request: Request):
    data = await request.json()
    count = data.get("count", 10)
    genres = data.get("genres")
    # Call the existing pick_songs function
    pick_songs(count, genres)
    # Return the new playlist (same format as /playlist)
    playlist = []
    for idx, f in enumerate(player.playlist):
        tags = player.tags_cache.get(f) or get_tags(f)
        title = tags.get('title', os.path.basename(f))
        artist = tags.get('artist', '')
        album = tags.get('album', '')
        year = tags.get('year', '')
        genres = tags.get('genres', [])
        cover_url = None
        cover_path = get_cover_path(f)
        if cover_path:
            cover_url = f"/cover/{idx}"
        playlist.append({
            "index": idx,
            "title": title,
            "artist": artist,
            "album": album,
            "year": year,
            "genres": genres,
            "audio_url": f"/audio/{idx}?cache={int(time.time() * 1000 + random.randint(1, 10000))}",
            "lyrics_url": f"/lyrics/{idx}",
            "cover_url": cover_url
        })
    return JSONResponse(playlist)

# Mount Gradio UI at /gradio
app = gr.mount_gradio_app(app, demo, path="/gradio")

# --- Create a safer web version without admin controls ---
def create_web_interface():
    web_interface = gr.Blocks(theme=THEME_MAP.get(_selected_theme, gr.themes.Soft()), css="""
    /* Make the play button green and pause button red in the audio player */
    audio::-webkit-media-controls-play-button {
        background-color: #27ae60 !important; /* green */
        border-radius: 50%;
    }
    audio:paused::-webkit-media-controls-play-button {
        background-color: #e74c3c !important; /* red when paused */
    }
    audio:-webkit-media-controls-play-button {
        color: white !important;
    }

    /* Compact action buttons */
    .small-btn button {
        min-width: 70px !important;
        max-width: 100px !important;
        width: auto !important;
        padding: 0.1em 0.7em !important;
        font-size: 0.9em !important;
    }
    """)
    
    with web_interface:
        gr.Markdown("# Random Music Player Web")
        with gr.Tabs():
            # --- New WaveSurfer Player tab ---
            with gr.Tab("Player"):
                # Embed the custom player as an iframe for full JS/CSS isolation
                gr.HTML('<iframe id="wavesurfer-iframe" src="/static/player.html" style="width:100%;height:auto;min-height:1200px;max-height:95vh;border:none;max-width:100%;margin:auto;display:block;"></iframe>')
                gr.HTML('''<script>
    (function() {
        function sendThemeToIframe() {
            var theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
            var iframe = document.getElementById('wavesurfer-iframe');
            if (iframe && iframe.contentWindow) {
                iframe.contentWindow.postMessage({type: 'set-theme', theme: theme}, '*');
            }
        }
        // Send on load
        window.addEventListener('DOMContentLoaded', sendThemeToIframe);
        // Send on theme change (Gradio toggles .dark on <html>)
        const observer = new MutationObserver(sendThemeToIframe);
        observer.observe(document.documentElement, {attributes: true, attributeFilter: ['class']});
        // Also send after a short delay in case iframe loads late
        setTimeout(sendThemeToIframe, 1000);
    })();
    </script>''')

            # --- Renamed tab with limited controls ---
            with gr.Tab("Create playlist"):
                gr.Markdown(r"""
    **Tip:** You can enter multiple music folder paths, separated by commas or semicolons.<br>
    **Example:**
    ```
    \\BuiDS\musik\24bit_flac; \\BuiDS\musik\16bit
    ```
    (You can use either forward or backslashes for paths.)
    """)
                # Load folder input value and scan data from cache if available
                _folder_input_value = None
                try:
                    _cache = load_scan_cache()
                    if _cache and _cache.get("folder_input_value"):
                        _folder_input_value = _cache["folder_input_value"]
                except Exception:
                    _folder_input_value = None
                folder_input = gr.Textbox(
                    label="Music Folder Paths",
                    placeholder=r"e.g. D:/Music1, D:/Music2; \\BuiDS\musik",
                    value=_folder_input_value or ""
                )
                
                with gr.Row():
                    scan_btn = gr.Button("Scan Folders", elem_classes="small-btn")
                    refresh_btn = gr.Button("Refresh Playlist / Genres", elem_classes="small-btn")
                # No clear cache button in this interface
                status_text = gr.Textbox(label="Status", interactive=False, value="", visible=True)

                # Create local pick count for the web interface
                pick_count_web = gr.Number(value=load_pick_count(), label="Number of Songs to Pick", precision=0)
                
                # Collapsible genre filter section
                with gr.Accordion("📋 Genre Filters (click to expand)", open=False):
                    genre_choices = sorted(list(player.genres)) if getattr(player, 'genres', None) else []
                    genre_dropdown = gr.CheckboxGroup(choices=genre_choices, label="Filter by Genre", interactive=True)
                    update_genre_btn = gr.Button("Apply Genre Filter", elem_classes="small-btn")
                
                with gr.Row():
                    pick_songs_btn = gr.Button("Pick songs", elem_classes="small-btn")

                # Set initial song count if scan data is restored
                _song_count_value = f"Total songs found: {len(player.audio_files)}" if getattr(player, 'audio_files', None) else ""
                song_count_text = gr.Textbox(label="Song Count", interactive=False, value=_song_count_value)
                playlist_table = gr.Dataframe(headers=["#", "Title", "Artist", "Album", "Genres"], interactive=False, label="Playlist")

                scan_btn.click(
                    fn=start_background_scan,
                    inputs=[folder_input],
                    outputs=[song_count_text, genre_dropdown, status_text]
                )
                refresh_btn.click(
                    fn=refresh_playlist_and_genres,
                    outputs=[song_count_text, genre_dropdown, status_text]
                )
                update_genre_btn.click(
                    fn=lambda genres: f"Total songs found: {len(player.filter_by_genre(genres))}",
                    inputs=[genre_dropdown],
                    outputs=[song_count_text]
                )
                # Connect the Pick songs button - simple pre-LLM style
                def pick_and_update_table_web(n, genres):
                    # Simple function like before LLM integration
                    if not n:
                        n = 10
                    try:
                        n = int(n)
                    except (ValueError, TypeError):
                        n = 10
                    
                    # Set autoplay flag
                    player.autoplay_next = True
                    
                    # Ensure we're using completely randomized selection with unique songs
                    import random
                    import time
                    import os
                    
                    # Generate a truly unique seed based on multiple factors
                    random_seed = int(time.time() * 1000) + os.getpid() + random.randint(1, 1000000)
                    random.seed(random_seed)
                    print(f"Using random seed: {random_seed}")
                    
                    # Get all available audio files
                    all_files = player.audio_files.copy()
                    
                    # Apply genre filtering if needed
                    if genres:
                        filtered = [f for f in all_files if any(g in player.tags_cache.get(f, {}).get('genres', []) for g in genres)]
                    else:
                        filtered = all_files
                    
                    # Make sure we have enough songs
                    if not filtered:
                        print("No songs match the selected genres")
                        return player.get_playlist_table(), ""
                    
                    # Create a truly random order by sorting with a random key
                    filtered.sort(key=lambda _: random.random())
                    
                    # Take the requested number of songs
                    if len(filtered) <= n:
                        selected_songs = filtered.copy()
                    else: 
                        selected_songs = filtered[:n]
                    
                    # Double-check we're not accidentally picking the same songs
                    current_titles = [player.tags_cache.get(song, {}).get('title', 'Unknown') for song in player.playlist]
                    new_titles = [player.tags_cache.get(song, {}).get('title', 'Unknown') for song in selected_songs]
                    
                    print(f"Current playlist: {current_titles[:3]}")
                    print(f"New playlist: {new_titles[:3]}")
                    
                    if current_titles and new_titles and current_titles[0] == new_titles[0]:
                        print("WARNING: First song is the same as before! Reshuffling...")
                        # Try again with a different random order
                        random.seed(random_seed + 1)
                        filtered.sort(key=lambda _: random.random())
                        selected_songs = filtered[:n] if len(filtered) > n else filtered.copy()
                    
                    # Update the player's playlist
                    player.playlist = selected_songs
                    player.current = 0
                    
                    # Print to server log to verify we're getting different songs
                    print(f"Selected {len(player.playlist)} random songs:")
                    for i, song in enumerate(player.playlist[:3]):
                        title = player.tags_cache.get(song, {}).get('title', 'Unknown')
                        print(f"  {i+1}. {title}")
                    
                    # Use a unique timestamp to ensure the browser doesn't cache the response
                    import time
                    timestamp = str(time.time())
                    
                    # Add script with unique timestamp to force a complete refresh
                    # Include the new_playlist parameter to force generation of a new playlist
                    js_code = f'''
                    <script>
                    // Force a complete refresh with unique ID: {timestamp}
                    setTimeout(function() {{
                        // First clear any cached playlist data
                        localStorage.removeItem('wavesurfer_playlist');
                        
                        const iframe = document.getElementById('wavesurfer-iframe');
                        if (iframe && iframe.contentWindow) {{
                            // Tell the player we want a new playlist with this refresh
                            iframe.contentWindow.postMessage({{type: 'refresh-and-play', timestamp: '{timestamp}', newPlaylist: true}}, '*');
                            console.log('Sending refresh command with timestamp', '{timestamp}');
                        }}
                    }}, 500);
                    </script>
                    '''
                    
                    # Return new playlist table and refresh script
                    return player.get_playlist_table(), gr.update(value=js_code)
                
                autoplay_script_web = gr.HTML(visible=True)
                
                pick_songs_btn.click(
                    fn=pick_and_update_table_web,
                    inputs=[pick_count_web, genre_dropdown],
                    outputs=[playlist_table, autoplay_script_web]
                )

            # Chat interface tab for web
            with gr.Tab("Chat"):
                gr.Markdown("### Chat with AI to control your music player")
                chat_history_web = gr.Chatbot(height=400, label="Chat History", type="messages")
                
                with gr.Row():
                    chat_input_web = gr.Textbox(label="Ask the AI to pick songs or filter by genre", placeholder="Example: Play 5 random rock songs", lines=2)
                    chat_submit_web = gr.Button("Send", variant="primary")
                
                with gr.Row():
                    chat_status_web = gr.Markdown("")
                
                def chat_and_pick_songs_web(message, history):
                    # Check if OpenRouter integration is available
                    if parse_genre_request is None:
                        return history + [{"role": "assistant", "content": "OpenRouter integration is not available. Please make sure openrouter_utils.py is in the same directory."}], ""
                    
                    # Check if API key is set
                    api_key = load_api_key()
                    if not api_key:
                        return history + [{"role": "assistant", "content": "No API key found. Please contact the administrator to set up the OpenRouter API key."}], ""
                    
                    # Get available genres
                    available_genres = sorted(list(player.genres)) if player.genres else []
                    if not available_genres:
                        return history + [{"role": "assistant", "content": "No genres found. Please scan your music folders first."}], ""
                    
                    # Add request to history
                    new_history = history + [{"role": "assistant", "content": "Thinking..."}]
                    
                    try:
                        # Parse the request for genres, count or duration, and year range
                        selected_genres, num_songs, duration, year_start, year_end, title_keywords, album_filters, error = parse_genre_request(message, available_genres)
                        
                        if error:
                            new_history[-1]["content"] = f"Error: {error}"
                            return new_history, ""
                        
                        # Ensure at least a count or duration
                        if duration is None and num_songs is None:
                            new_history[-1]["content"] = "Error: could not determine song count or duration. Please specify one."
                            return new_history, ""
                        
                        # Pick by duration if specified, otherwise by count
                        if duration:
                            pick_songs_by_duration(duration, selected_genres, year_start, year_end, title_keywords, album_filters)
                            yr_text = ""
                            if year_start and year_end:
                                yr_text = f" between {year_start} and {year_end}"
                            elif year_start:
                                yr_text = f" from {year_start} onward"
                            elif year_end:
                                yr_text = f" up to {year_end}"
                            response = f"Playing ~{duration} minutes of {', '.join(selected_genres)} songs{yr_text}. The music will start momentarily."
                        else:
                            pick_songs_by_filters(num_songs, selected_genres, title_keywords, album_filters, year_start, year_end)
                            response = f"Playing {num_songs} songs from filters: {', '.join(selected_genres)}{(' with titles '+', '.join(title_keywords)) if title_keywords else ''}{(' from albums '+', '.join(album_filters)) if album_filters else ''}. The music will start momentarily."
                        
                        return new_history, "", gr.update(value=f"<script>setTimeout(function() {{ console.log('Refreshing player...'); window.location.reload(); }}, 1000);</script>")
                        
                    except Exception as e:
                        new_history[-1]["content"] = f"An error occurred: {str(e)}"
                        return new_history, ""
                
                chat_submit_web.click(
                    fn=chat_and_pick_songs_web,
                    inputs=[chat_input_web, chat_history_web],
                    outputs=[chat_history_web, chat_input_web]
                )
                chat_input_web.submit(
                    fn=chat_and_pick_songs_web,
                    inputs=[chat_input_web, chat_history_web],
                    outputs=[chat_history_web, chat_input_web]
                )
                
                gr.Markdown("""
                ### Example phrases:
                - "Play 5 random jazz songs"  
                - "I want to listen to some rock and metal music"  
                - "Create a playlist with 15 classical and ambient songs"  
                - "Pick some electronic tracks"  
                """)
            
            # Simplified Settings tab with just the pick count parameter
            with gr.Tab("Settings"):
                gr.Markdown("### General Settings")
                with gr.Row():
                    pick_count_web = gr.Number(value=load_pick_count(), label="Number of Songs to Pick", precision=0)
                pick_count_web.change(fn=save_pick_count, inputs=[pick_count_web], outputs=[pick_count_web])
                gr.Markdown("Set how many random songs to pick when you use the 'Pick songs' button in the Player tab.")

    return web_interface

# Create and mount the web interface at /web path
web_interface = create_web_interface()
app = gr.mount_gradio_app(app, web_interface, path="/web")

# --- End Hybrid API endpoints ---

# Create an endpoint for direct playlist refresh without needing iframe messaging
@app.get("/direct-refresh-playlist")
async def direct_refresh_playlist(autoplay: bool = True, api: str = "web"):
    """Endpoint that directly refreshes the player by redirecting to the player page
    
    Parameters:
        autoplay: Whether to start playing after refresh (default: True)
        api: Which API is calling this (web or gradio)
    """
    # Set the autoplay flag in the player's data cache to ensure it starts playing
    # This ensures both APIs can trigger autoplay
    if hasattr(player, 'autoplay_next'):
        player.autoplay_next = autoplay
    
    # Log the refresh request
    print(f"Direct refresh requested: autoplay={autoplay}, api={api}, time={int(time.time())}")
    
    # Create a simple HTML response that will redirect to the player
    # and force a reload of the playlist with autoplay
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="0;url=/static/player.html?refresh=1&autoplay=1&ts={int(time.time())}&source={api}" />
    </head>
    <body>
        <p>Refreshing player...</p>
        <script>
            console.log("Redirecting to player with autoplay...");
        </script>
    </body>
    </html>
    """
    return Response(content=html_content, media_type="text/html")

# Inject favicon using custom HTML
favicon_html = """
<link rel="icon" type="image/x-icon" href="favicon.ico">
"""
gr.HTML(favicon_html)

# Run with: uvicorn music_player_gradio:app --host 0.0.0.0 --port 7860