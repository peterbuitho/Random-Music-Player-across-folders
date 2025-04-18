# Gradio-based Music Player (browser UI)
# Ported from tkinter version
import os
import random
import gradio as gr
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
import requests
import re

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
    
    return tags

LYRICS_API = "https://api.lyrics.ovh/v1/{artist}/{title}"
def fetch_lyrics(artist, title):
    try:
        url = LYRICS_API.format(artist=artist, title=title)
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('lyrics', '')
    except Exception:
        pass
    return ""

# --- Gradio App Logic ---

AUDIO_EXTS = (".mp3", ".flac")

def pick_songs(n, genres=None):
    import random
    try:
        n = int(n)
    except Exception:
        n = 10
    if n <= 0:
        n = 10
    # If genres are specified, filter playlist accordingly
    if genres:
        filtered = [f for f in player.audio_files if any(g in player.tags_cache.get(f, {}).get('genres', []) for g in genres)]
    else:
        filtered = player.audio_files.copy()
    if len(filtered) <= n:
        player.playlist = filtered.copy()
        player.current = 0
        return player.get_playlist_table()
    player.playlist = random.sample(filtered, n)
    player.current = 0
    return player.get_playlist_table()


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

    def scan_files(self, folders):
        self.folders = folders
        self.audio_files = get_audio_files(folders, AUDIO_EXTS)
        self.tags_cache = {}
        genre_set = set()
        for i, f in enumerate(self.audio_files):
            tags = get_tags(f)
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
            # Always return the genre list, even if empty
            return self.get_playlist_table(), sorted(list(self.genres))
        random.shuffle(self.playlist)
        self.current = 0
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
        for idx, f in enumerate(self.playlist):
            tags = self.tags_cache.get(f) or get_tags(f)
            title = tags.get('title', os.path.basename(f))
            artist = tags.get('artist', '')
            album = tags.get('album', '')
            genres = ', '.join(tags.get('genres', []))
            rows.append([idx+1, title, artist, album, genres])
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
        lyrics = fetch_lyrics(artist, title) if artist and title else ""
        return audio_url, title, artist, lyrics

    def next(self):
        if self.current < len(self.playlist) - 1:
            self.current += 1
        return self.play()

    def prev(self):
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
    gr.Markdown(r"""
**Tip:** You can enter multiple music folder paths, separated by commas or semicolons.<br>
**Example:**
```
D:/Music1, D:/Music2; \\BuiDS\musik
```
(You can use either forward or backslashes for paths.)
""")
    with gr.Tabs():
        with gr.Tab("Player"):
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

            genre_choices = sorted(list(player.genres)) if getattr(player, 'genres', None) else []
            genre_dropdown = gr.CheckboxGroup(choices=genre_choices, label="Filter by Genre", interactive=True)
            with gr.Row():
                update_genre_btn = gr.Button("Apply Genre Filter", elem_classes="small-btn")
                pick_songs_btn = gr.Button("Pick songs", elem_classes="small-btn")

            # Set initial song count if scan data is restored
            _song_count_value = f"Total songs found: {len(player.audio_files)}" if getattr(player, 'audio_files', None) else ""
            song_count_text = gr.Textbox(label="Song Count", interactive=False, value=_song_count_value)
            playlist_table = gr.Dataframe(headers=["#", "Title", "Artist", "Album", "Genres"], interactive=False, label="Playlist")
            song_number_input = gr.Number(value=1, label="Song Number to Play (1-based)", precision=0)

            with gr.Row():
                prev_btn = gr.Button("Previous")
                play_btn = gr.Button("Play")
                next_btn = gr.Button("Next")

            audio = gr.Audio(label="Now Playing", interactive=False, autoplay=True)
            song_title = gr.Textbox(label="Title", interactive=False)
            song_artist = gr.Textbox(label="Artist", interactive=False)
            lyrics_box = gr.Textbox(label="Lyrics", lines=8, interactive=False)

            # Update song selector choices after scanning or picking songs
            def update_song_selector_table():
                choices = []
                for idx, f in enumerate(player.playlist):
                    tags = player.tags_cache.get(f) or get_tags(f)
                    title = tags.get('title', os.path.basename(f))
                    artist = tags.get('artist', '')
                    display = f"{idx+1}. {title} - {artist}" if artist else f"{idx+1}. {title}"
                    choices.append(display)
            scan_btn.click(fn=start_background_scan, inputs=[folder_input], outputs=[song_count_text, genre_dropdown, status_text])
            refresh_btn.click(fn=refresh_playlist_and_genres, outputs=[song_count_text, genre_dropdown, status_text])
            clear_cache_btn.click(fn=clear_cache, outputs=[song_count_text, genre_dropdown, status_text])
            update_genre_btn.click(
                fn=lambda genres: f"Total songs found: {len(player.filter_by_genre(genres))}",
                inputs=[genre_dropdown],
                outputs=[song_count_text]
            )
            pick_songs_btn.click(
                fn=lambda n, genres: pick_songs(n, genres),
                inputs=[pick_count, genre_dropdown],
                outputs=[playlist_table]
            )

        with gr.Tab("Settings"):
            gr.Markdown("### General Settings")
            with gr.Row():
                pick_count.render()
            pick_count.change(fn=save_pick_count, inputs=[pick_count], outputs=[pick_count])
            gr.Markdown("Set how many random songs to pick when you use the 'Pick songs' button in the Player tab.")
            # --- Theme selector UI ---
            def set_theme(new_theme):
                save_theme(new_theme)
                return f"Theme set to {new_theme}. Please reload the app to apply."
            theme_dropdown = gr.Dropdown(["Default", "Soft", "Monochrome"], value=_selected_theme, label="Gradio Theme", interactive=True)
            theme_status = gr.Markdown(visible=False)
            def _show_theme_status(theme):
                return gr.update(visible=True), f"Theme set to {theme}. Please reload the app to apply."
            theme_dropdown.change(fn=set_theme, inputs=[theme_dropdown], outputs=[theme_status])
            theme_dropdown.change(fn=_show_theme_status, inputs=[theme_dropdown], outputs=[theme_status])
            # --- Restart server button ---
            import sys
            def restart_server():
                import os
                import time
                # Show message before restarting
                time.sleep(0.5)
                os.execl(sys.executable, sys.executable, *sys.argv)
            restart_btn = gr.Button("Restart Server", elem_classes="small-btn")
            restart_status = gr.Markdown(visible=False)
            def show_restarting():
                return gr.update(visible=True), "Restarting server... Please reload your browser in a few seconds."
            restart_btn.click(fn=restart_server, outputs=[])
            restart_btn.click(fn=show_restarting, outputs=[restart_status])
            # --- End restart button ---

allowed_paths = get_allowed_paths()
demo.launch(allowed_paths=allowed_paths, inbrowser=True, share=True)
folder_input = gr.Textbox(
    label="Music Folder Paths",
    placeholder=r"e.g. D:/Music1, D:/Music2; \\BuiDS\musik",
    value=_folder_input_value or ""
)
allowed_paths = get_allowed_paths()
demo.launch(allowed_paths=allowed_paths, inbrowser=True, share=True)
