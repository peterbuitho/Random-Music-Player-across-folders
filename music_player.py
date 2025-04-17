import os
import random
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from PIL import Image, ImageTk
import vlc
import requests
import io
from persistence_utils import save_selected_folders, load_selected_folders, save_tags_cache, load_tags_cache

# Helper to get all audio files recursively
def get_audio_files(folders, exts=(".mp3", ".flac")):
    files = []
    for folder in folders:
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                if f.lower().endswith(exts):
                    files.append(os.path.join(root, f))
    return files

# Helper to extract tags
import re

def get_tags(filepath):
    audio = File(filepath)
    tags = {}
    if audio is None:
        return tags
    # Common tags
    for tag in ["title", "artist", "album", "genre", "lyrics", "lyric"]:
        v = audio.tags.get(tag) if audio.tags else None
        if v:
            tags[tag] = str(v[0]) if isinstance(v, list) else str(v)
    # Genre splitting
    if 'genre' in tags:
        genres = re.split(r'[;|,/\\>\-]+', tags['genre'])
        genres = [g.strip() for g in genres if g.strip()]
        tags['genres'] = genres
    else:
        tags['genres'] = []
    # Cover art
    cover = None
    if isinstance(audio, FLAC):
        if audio.pictures:
            cover = audio.pictures[0].data
    elif isinstance(audio, MP3):
        for k in audio.tags.keys():
            if k.startswith('APIC'):
                cover = audio.tags[k].data
    tags['cover'] = cover
    return tags

# Fetch lyrics from internet
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

class PlayerApp:
    CONFIG_FILE = ".music_player_config"
    FONT_FAMILY = "Segoe UI"
    FONT_SIZES = {
        "default": 11,
        "small": 9,
        "medium": 10,
        "large": 12,
        "xlarge": 14
    }
    FONT_STYLES = {
        "normal": (),
        "bold": ("bold",),
        "italic": ("italic",),
        "bold_italic": ("bold", "italic")
    }
    # Example: self.fonts["label"] = (FONT_FAMILY, FONT_SIZES["medium"], "bold")
    def font(self, size_key="default", style_key="normal"):
        return (self.FONT_FAMILY, self.FONT_SIZES[size_key], *self.FONT_STYLES[style_key])

    def __init__(self, root):
        self.root = root
        self.root.title("Random Music Player")
        self.folders = load_selected_folders()
        self.audio_files = []
        self.filtered_files = []
        self.playlist = []
        self.current = 0
        self.player = None
        self.genres = set()
        self.genre_vars = {}
        self.tags_cache = load_tags_cache()  # Caches tags by file path
        self.last_parent_folder = self.load_last_folder()  # Persist last selected parent folder
        self.setup_ui()
        self.update_folders_listbox()
        self.scan_files()

    def update_song_count_by_genre(self):
        """
        Update the total available songs label based on selected genres.
        """
        if not hasattr(self, 'song_count_label'):
            return
        selected_genres = [g for g, v in self.genre_vars.items() if v.get()]
        if not selected_genres:
            count = len(self.audio_files)
        else:
            count = 0
            for f in self.audio_files:
                try:
                    tags = self.tags_cache.get(f)
                    if tags is None:
                        tags = get_tags(f)
                        self.tags_cache[f] = tags
                    genres = tags.get('genres', [])
                    if any(g in selected_genres for g in genres):
                        count += 1
                except Exception:
                    continue  # Skip invalid/corrupt files
        self.song_count_label.config(text=f"Total songs: {count}")


    def load_last_folder(self):
        try:
            config_path = os.path.join(os.path.dirname(__file__), self.CONFIG_FILE)
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    folder = f.read().strip()
                    if os.path.isdir(folder):
                        return folder
        except Exception:
            pass
        return None

    def save_last_folder(self, folder):
        try:
            config_path = os.path.join(os.path.dirname(__file__), self.CONFIG_FILE)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(folder)
        except Exception:
            pass

    def setup_ui(self):

        def set_font_size(newsize):
            self.playlist_box.config(font=(self.FONT_FAMILY, int(newsize)))
            self.lyrics_text.config(font=(self.FONT_FAMILY, int(newsize)))

        self.update_font_size = lambda: set_font_size(self.font_size_var.get())
        self.root.title("Random Music Player")
        self.root.geometry("1000x900")
        self.root.minsize(700, 600)
        self.root.rowconfigure(4, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.configure(bg="#232323")

        # Style settings
        bg_main = "#232323"  # dark grey
        bg_panel = "#32343a"  # slightly lighter dark grey
        bg_list = "#232323"   # match main bg for lists
        fg_main = "#eaeaea"
        fg_label = "#eaeaea"
        btn_bg = "#3a3f4b"
        btn_fg = "#eaeaea"
        entry_bg = "#232323"
        entry_fg = "#eaeaea"
        accent = "#b8c1ec"
        play_green = "#27ae60"
        stop_red = "#e74c3c"
        pick_yellow = "#e1b000"  # dark yellow
        nav_grey = "#cccccc"     # light grey

        # Folder selection
        folder_frame = tk.Frame(self.root, bg=bg_panel, relief="groove", bd=3)
        folder_frame.grid(row=0, column=0, sticky="ew", pady=5, padx=5)
        folder_frame.columnconfigure(7, weight=1)
        # Add and change parent folder controls
        folder_btn = tk.Button(folder_frame, text="Add Folders", command=self.select_folders, bg=btn_bg, fg=btn_fg,
                               relief="raised", bd=3, activebackground=accent)
        folder_btn.grid(row=0, column=0, padx=2, pady=3)
        change_parent_btn = tk.Button(folder_frame, text="Change Parent Folder", command=self.change_parent_folder,
                                      bg=btn_bg, fg=btn_fg, relief="raised", bd=3, activebackground=accent)
        change_parent_btn.grid(row=0, column=1, padx=2, pady=3)
        self.parent_folder_label = tk.Label(folder_frame, text="Parent: " + (self.last_parent_folder or "Not set"),
                                            bg=bg_panel, fg=accent, font=self.font("medium", "italic"))
        self.parent_folder_label.grid(row=0, column=2, padx=5, pady=3, sticky="w")
        # Folder list controls
        clear_btn = tk.Button(folder_frame, text="Clear Folders", command=self.clear_folders, bg=btn_bg, fg=btn_fg,
                              relief="raised", bd=3, activebackground=accent)
        clear_btn.grid(row=0, column=3, padx=2, pady=3)
        remove_btn = tk.Button(folder_frame, text="Remove Selected", command=self.remove_selected_folders, bg=btn_bg,
                               fg=btn_fg, relief="raised", bd=3, activebackground=accent)
        remove_btn.grid(row=0, column=4, padx=2, pady=3)
        # Move selected folders label, listbox, and scrollbar to row 1
        self.selected_folders_label = tk.Label(folder_frame, text="Selected Folders (0):", bg=bg_panel, fg=fg_label,
                 font=self.font("medium", "bold"))
        self.selected_folders_label.grid(row=1, column=0, padx=5, pady=(2,2), sticky="w", columnspan=2)
        folders_scroll = tk.Scrollbar(folder_frame, orient="vertical")
        self.folders_listbox = tk.Listbox(folder_frame, height=3, width=60, selectmode=tk.MULTIPLE,
                                          yscrollcommand=folders_scroll.set, bg=bg_list, fg=fg_main,
                                          relief="sunken", bd=2, highlightbackground=accent,
                                          selectbackground=accent)
        folders_scroll.config(command=self.folders_listbox.yview)
        self.folders_listbox.grid(row=1, column=2, padx=2, pady=2, sticky="ew", columnspan=5)
        folders_scroll.grid(row=1, column=7, padx=2, pady=2, sticky="ns")
        folder_frame.columnconfigure(2, weight=1)

        # Genre selection
        genre_bg = "#f0f0f0"
        # Foldable genre section
        self.genre_visible = tk.BooleanVar(value=True)
        def toggle_genre_frame():
            if self.genre_visible.get():
                self.genre_frame.grid()
                self.genre_toggle_btn.config(text="Hide Genres")
            else:
                self.genre_frame.grid_remove()
                self.genre_toggle_btn.config(text="Show Genres")
        self.genre_frame = tk.LabelFrame(self.root, text="Genres", bg=genre_bg, fg="#232323", relief="groove", bd=3, font=self.font("medium", "bold"))
        self.genre_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.genre_bg = genre_bg  # Store for later use

        # Number of songs
        num_frame = tk.Frame(self.root, bg=bg_panel, relief="groove", bd=2)
        num_frame.grid(row=2, column=0, sticky="ew", padx=5)
        tk.Label(num_frame, text="Number of Songs:", bg=bg_panel, fg=fg_label, font=self.font("medium")).pack(side="left", padx=2, pady=2)
        self.num_entry = tk.Entry(num_frame, width=5, bg=entry_bg, fg=entry_fg, relief="sunken", bd=2)
        self.num_entry.pack(side="left", padx=2, pady=2)
        self.num_entry.insert(0, "10")
        pick_btn = tk.Button(num_frame, text="Pick Songs", command=self.pick_songs, bg=pick_yellow, fg="black", relief="raised", bd=3, activebackground=pick_yellow)
        pick_btn.pack(side="left", padx=5, pady=2)
        shuffle_btn = tk.Button(num_frame, text="Shuffle", command=self.shuffle_playlist, bg=nav_grey, fg="#232323", relief="raised", bd=2, font=self.font("small"))
        shuffle_btn.pack(side="left", padx=(2,5), pady=2)
        # Total duration next to Pick Songs button
        self.duration_label = tk.Label(num_frame, text="Total duration: 0 min", bg=bg_panel, fg=accent, font=self.font("medium", "bold"))
        self.duration_label.pack(side="left", padx=5, pady=2)
        # Total number of songs, right-aligned
        self.song_count_label = tk.Label(num_frame, text=f"Total songs: 0", bg=bg_panel, fg=accent, font=self.font("medium", "bold"), anchor="e", justify="right")
        self.song_count_label.pack(side="right", padx=(5,0), pady=2)
        self.genre_toggle_btn = tk.Button(num_frame, text="Hide Genres", command=lambda: (self.genre_visible.set(not self.genre_visible.get()), toggle_genre_frame()), bg=genre_bg, fg="#232323", relief="raised", bd=2, font=self.font("small"))
        self.genre_toggle_btn.pack(side="right", padx=(10,5), pady=2)


        # Font size control (must be after lyrics_text is created)
        font_frame = tk.Frame(self.root, bg=bg_panel)
        font_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=(0,0))
        font_frame.columnconfigure(0, weight=1)
        right_inner = tk.Frame(font_frame, bg=bg_panel)
        right_inner.grid(row=0, column=1, sticky="e")
        tk.Label(right_inner, text="Font Size:", bg=bg_panel, fg=fg_label, font=self.font("medium")).pack(side="left", padx=(0,2))
        self.font_size_var = tk.IntVar(value=11)
        def _update_font_size():
            size = self.font_size_var.get()
            self.playlist_box.config(font=(self.FONT_FAMILY, size))
            self.lyrics_text.config(font=(self.FONT_FAMILY, size))
        font_spin = tk.Spinbox(right_inner, from_=8, to=24, width=3, textvariable=self.font_size_var, command=_update_font_size, font=self.font("medium"))
        font_spin.pack(side="left")
        self.update_font_size = _update_font_size

        # PanedWindow for resizable playlist and info/lyrics
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief="raised", bg=bg_panel, sashwidth=8, showhandle=True)
        main_pane.grid(row=4, column=0, rowspan=3, sticky="nsew", padx=5, pady=5)
        self.root.grid_rowconfigure(4, weight=1)
        self.root.grid_rowconfigure(5, weight=0)
        self.root.grid_rowconfigure(6, weight=2)
        self.main_pane = main_pane  # Store for later sash adjustment

        # Playlist with scrollbar
        playlist_frame = tk.Frame(main_pane, bg=bg_panel, relief="groove", bd=3)
        playlist_scroll = tk.Scrollbar(playlist_frame, orient="vertical")
        self.playlist_box = tk.Listbox(playlist_frame, width=60, yscrollcommand=playlist_scroll.set, bg=bg_list, fg="#eaeaea", relief="sunken", bd=2, highlightbackground=accent, selectbackground=accent, font=self.font())
        playlist_scroll.config(command=self.playlist_box.yview)
        self.playlist_box.pack(side="left", fill="both", expand=True, padx=3, pady=3)
        playlist_scroll.pack(side="right", fill="y")
        self.playlist_box.bind('<<ListboxSelect>>', self.on_select)

        # Song info (cover + lyrics with scrollbar)
        info_frame = tk.Frame(main_pane, bg=bg_panel, relief="groove", bd=3)
        cover_frame = tk.Frame(info_frame, bg=bg_panel, width=300, height=220)
        cover_frame.pack_propagate(False)
        cover_frame.pack(side="left", padx=5, anchor="n")
        self.cover_label = tk.Label(cover_frame, bg=bg_panel)
        self.cover_label.pack(side="top", anchor="n")
        self.song_title_label = tk.Label(cover_frame, text="", bg=bg_panel, fg=accent, font=self.font("large", "bold"), wraplength=280, justify="center")
        self.song_title_label.pack(side="top", anchor="n")
        self.cover_frame = cover_frame  # For later use

        # Progress bar under cover/title (bright style for visibility)
        import tkinter.ttk as ttk
        self.progress_var = tk.DoubleVar()
        style = ttk.Style()
        style.theme_use('default')
        style.configure('Custom.Horizontal.TProgressbar',
                        troughcolor=bg_panel,
                        bordercolor=accent,
                        background='#27ae60',  # bright green
                        lightcolor='#b8c1ec',
                        darkcolor='#27ae60',
                        thickness=7)
        self.progress_bar = ttk.Progressbar(cover_frame, variable=self.progress_var, orient="horizontal", mode="determinate", length=120, style='Custom.Horizontal.TProgressbar')
        self.progress_bar.pack(side="top", fill="x", padx=5, pady=(8,2))
        # Bind mouse events for seeking
        self.progress_bar.bind('<Button-1>', self.on_progress_click)
        self.progress_bar.bind('<B1-Motion>', self.on_progress_drag)
        self.progress_bar.bind('<ButtonRelease-1>', self.on_progress_release)
        self._progress_dragging = False
        # Song remaining time label under progress bar, right aligned
        self.song_time_label = tk.Label(cover_frame, text="", bg=bg_panel, fg=accent, font=self.font("small", "italic"), anchor="e", width=12, justify="right")
        self.song_time_label.pack(side="top", fill="x", padx=5, pady=(0,6))
        lyrics_frame = tk.Frame(info_frame, bg=bg_panel)
        lyrics_frame.pack(side="left", fill="both", expand=True)
        lyrics_scroll = tk.Scrollbar(lyrics_frame, orient="vertical")
        self.lyrics_text = tk.Text(lyrics_frame, height=10, width=50, wrap="word", yscrollcommand=lyrics_scroll.set, bg=bg_list, fg=fg_main, relief="sunken", bd=2, highlightbackground=accent, insertbackground=fg_main, font=self.font())
        lyrics_scroll.config(command=self.lyrics_text.yview)
        self.lyrics_text.pack(side="left", fill="both", expand=True, padx=3, pady=3)
        lyrics_scroll.pack(side="right", fill="y")

        # Add frames to PanedWindow
        main_pane.add(playlist_frame, minsize=120)
        main_pane.add(info_frame, minsize=200)

        # Set initial sash position to 1/5 of window width after mainloop starts
        def set_initial_sash():
            w = self.root.winfo_width()
            if w < 100:  # Not yet mapped, try again
                self.root.after(50, set_initial_sash)
                return
            # Use sash_place to move sash: sash_place(index, x, y)
            self.main_pane.sash_place(0, int(w/4), 0)
        self.root.after(100, set_initial_sash)

        # Playback controls
        ctrl_frame = tk.Frame(self.root, bg=bg_panel, relief="groove", bd=3)
        ctrl_frame.grid(row=7, column=0, pady=5, sticky="ew", padx=5)
        ctrl_frame.columnconfigure(0, weight=1)
        center_inner = tk.Frame(ctrl_frame, bg=bg_panel)
        center_inner.pack(side="left", anchor="center", expand=True)
        self.play_btn = tk.Button(center_inner, text="▶", command=self.play, bg=play_green, fg="white", relief="raised", bd=3, activebackground=play_green, font=self.font("xlarge", "bold"), width=8)
        self.play_btn.pack(side="left", padx=2, pady=2)
        tk.Button(center_inner, text="⏸", command=self.pause, bg=stop_red, fg="white", relief="raised", bd=3, activebackground=stop_red, font=self.font("xlarge", "bold")).pack(side="left", padx=2, pady=2)
        tk.Button(center_inner, text="⏮", command=self.prev, bg=nav_grey, fg="#232323", relief="raised", bd=3, activebackground=nav_grey, font=self.font("xlarge", "bold")).pack(side="left", padx=2, pady=2)
        tk.Button(center_inner, text="⏭", command=self.next, bg=nav_grey, fg="#232323", relief="raised", bd=3, activebackground=nav_grey, font=self.font("xlarge", "bold")).pack(side="left", padx=2, pady=2)
        # Volume slider right-aligned
        right_inner = tk.Frame(ctrl_frame, bg=bg_panel)
        right_inner.pack(side="right", anchor="e")
        tk.Label(right_inner, text="Volume:", bg=bg_panel, fg=fg_label, font=self.font("medium")).pack(side="left", padx=(2,2))
        self.volume_var = tk.IntVar(value=80)
        volume_slider = tk.Scale(right_inner, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.volume_var,
                                bg=bg_panel, fg=accent, troughcolor=bg_list, highlightthickness=0, showvalue=True, length=200)
        volume_slider.pack(side="left", padx=5)
        def on_volume_change(val):
            if self.player:
                try:
                    self.player.audio_set_volume(int(float(val)))
                except Exception:
                    pass
        self.volume_var.trace_add('write', lambda *args: on_volume_change(self.volume_var.get()))

    def change_parent_folder(self):
        parent = filedialog.askdirectory(mustexist=True, title="Select Parent Folder", parent=self.root)
        if parent:
            self.last_parent_folder = parent
            self.save_last_folder(parent)
            self.parent_folder_label.config(text="Parent: " + parent)

    def select_folders(self):
        parent = self.last_parent_folder
        if not parent or not os.path.isdir(parent):
            parent = filedialog.askdirectory(mustexist=True, title="Select Parent Folder", parent=self.root)
            if not parent:
                return
            self.last_parent_folder = parent
            self.save_last_folder(parent)
            self.parent_folder_label.config(text="Parent: " + parent)
        else:
            self.parent_folder_label.config(text="Parent: " + parent)
        subfolders = [os.path.join(parent, d) for d in os.listdir(parent) if os.path.isdir(os.path.join(parent, d))]
        subfolders.insert(0, parent)  # Include parent itself
        # Popup to select multiple folders
        sel_win = tk.Toplevel(self.root)
        sel_win.title("Select Folders")
        tk.Label(sel_win, text="Select one or more folders:").pack(padx=5, pady=5)
        frame = tk.Frame(sel_win)
        frame.pack(padx=5, pady=5)
        listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, width=80, height=min(15, len(subfolders)))
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        listbox.config(yscrollcommand=scrollbar.set)
        for f in subfolders:
            listbox.insert(tk.END, f)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        def select_all():
            listbox.select_set(0, tk.END)
        btn_frame = tk.Frame(sel_win)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Select All", command=select_all).pack(side="left", padx=5)
        def add_selected():
            selected = [subfolders[i] for i in listbox.curselection()]
            added = False
            for f in selected:
                if f not in self.folders:
                    self.folders.append(f)
                    added = True
            if added:
                save_selected_folders(self.folders)
                self.update_folders_listbox()
                # --- Spinner and counter ---
                spinner_win = tk.Toplevel(sel_win)
                spinner_win.title("Scanning Folders...")
                tk.Label(spinner_win, text="Scanning and analyzing files, please wait...").pack(padx=10, pady=10)
                from tkinter import ttk
                spinner = ttk.Progressbar(spinner_win, mode="indeterminate", length=220)
                spinner.pack(padx=10, pady=6)
                counter_label = tk.Label(spinner_win, text="0 / 0")
                counter_label.pack(pady=(0,10))
                spinner.start(10)
                spinner_win.update()
                # Run scan_files with counter
                def scan_with_counter():
                    files = get_audio_files(self.folders)
                    self.audio_files = files
                    self.genres = set()
                    tags_changed = False
                    total = len(files)
                    for i, f in enumerate(files):
                        try:
                            if f in self.tags_cache:
                                tags = self.tags_cache[f]
                            else:
                                tags = get_tags(f)
                                self.tags_cache[f] = tags
                                tags_changed = True
                            genres = tags.get('genres', [])
                            for g in genres:
                                self.genres.add(g)
                        except Exception:
                            continue
                        if i % 10 == 0 or i == total-1:
                            try:
                                if counter_label.winfo_exists():
                                    counter_label.config(text=f"{i+1} / {total}")
                                    spinner_win.update()
                            except tk.TclError:
                                pass  # Widget was destroyed, ignore
                    if tags_changed:
                        save_tags_cache(self.tags_cache)
                    # Update genre checkboxes
                    for widget in self.genre_frame.winfo_children():
                        widget.destroy()
                    self.genre_vars = {}
                    # Arrange genre checkboxes in a grid to fit the frame width
                    def layout_genre_checkboxes():
                        for widget in self.genre_frame.winfo_children():
                            widget.destroy()
                        self.genre_vars = {}
                        avg_cb_width = 120  # Adjust as needed
                        frame_width = self.genre_frame.winfo_width() or 600
                        n_cols = max(1, frame_width // avg_cb_width)
                        row, col = 0, 0
                        for g in sorted(self.genres):
                            var = tk.BooleanVar()
                            cb = tk.Checkbutton(self.genre_frame, text=g, variable=var)
                            cb.grid(row=row, column=col, sticky="w", padx=2, pady=2)
                            self.genre_vars[g] = var
                            col += 1
                            if col >= n_cols:
                                col = 0
                                row += 1
                    self.genre_frame.after(50, layout_genre_checkboxes)
                    def on_resize(event):
                        layout_genre_checkboxes()
                    self.genre_frame.bind("<Configure>", on_resize)
                    self.update_folders_listbox()
                    spinner.stop()
                    spinner_win.destroy()
                self.root.after(100, scan_with_counter)
            sel_win.destroy()
        tk.Button(btn_frame, text="Add Selected", command=add_selected).pack(side="left", padx=5)

    def scan_files(self):
        self.audio_files = get_audio_files(self.folders)
        # Update total song count label
        if hasattr(self, 'song_count_label'):
            self.update_song_count_by_genre()
        # Gather genres, skip invalid/corrupt files
        self.genres = set()
        tags_changed = False
        for f in self.audio_files:
            try:
                if f in self.tags_cache:
                    tags = self.tags_cache[f]
                else:
                    tags = get_tags(f)
                    self.tags_cache[f] = tags
                    tags_changed = True
                genres = tags.get('genres', [])
                for g in genres:
                    self.genres.add(g)
            except Exception:
                continue
        if tags_changed:
            save_tags_cache(self.tags_cache)
        # Update genre checkboxes
        for widget in self.genre_frame.winfo_children():
            widget.destroy()
        self.genre_vars = {}
        # Arrange genre checkboxes in a grid to fit the frame width
        def layout_genre_checkboxes():
            for widget in self.genre_frame.winfo_children():
                widget.destroy()
            self.genre_vars = {}
            # Estimate checkbox width (in pixels)
            avg_cb_width = 120  # Adjust as needed
            frame_width = self.genre_frame.winfo_width() or 600
            n_cols = max(1, frame_width // avg_cb_width)
            row, col = 0, 0
            for g in sorted(self.genres):
                var = tk.BooleanVar()
                def make_update_func():
                    # Closure to capture genre name
                    def update_count(*args):
                        self.update_song_count_by_genre()
                    return update_count
                cb = tk.Checkbutton(self.genre_frame, text=g, variable=var, bg=self.genre_bg, activebackground=self.genre_bg, fg="#232323", selectcolor=self.genre_bg)
                cb.grid(row=row, column=col, sticky="w", padx=2, pady=2)
                var.trace_add('write', make_update_func())
                self.genre_vars[g] = var
                col += 1
                if col >= n_cols:
                    col = 0
                    row += 1
        self.genre_frame.after(50, layout_genre_checkboxes)
        # Re-layout on window resize
        def on_resize(event):
            layout_genre_checkboxes()
        self.genre_frame.bind("<Configure>", on_resize)
        # Update folders listbox
        self.update_folders_listbox()

    def pick_songs(self):
        selected_genres = [g for g, v in self.genre_vars.items() if v.get()]
        # If no genre is selected, allow all genres
        if not selected_genres:
            filtered = list(self.audio_files)
        else:
            filtered = []
            for f in self.audio_files:
                try:
                    tags = self.tags_cache.get(f)
                    if tags is None:
                        tags = get_tags(f)
                        self.tags_cache[f] = tags
                    genres = tags.get('genres', [])
                    if any(g in selected_genres for g in genres):
                        filtered.append(f)
                except Exception:
                    continue
        n = int(self.num_entry.get() or 10)
        if len(filtered) < n:
            n = len(filtered)
        if n == 0:
            self.playlist_box.delete(0, tk.END)
            messagebox.showinfo("Info", "No songs available for the current selection.")
            return
        # Enforce no artist >60% of playlist unless not enough alternatives
        from collections import defaultdict
        import math
        # Build a mapping of artist to their songs
        artist_to_files = defaultdict(list)
        for f in filtered:
            try:
                tags = self.tags_cache.get(f) or get_tags(f)
                artist = tags.get('artist', '').strip() or 'Unknown Artist'
                artist_to_files[artist].append(f)
            except Exception:
                continue
        max_per_artist = max(1, int(math.ceil(0.6 * n)))
        playlist = []
        used = set()
        # First, try to fairly distribute songs
        # Shuffle artist order for fairness
        import random
        artists = list(artist_to_files.keys())
        random.shuffle(artists)
        # Add up to max_per_artist per artist, round-robin
        while len(playlist) < n:
            added_any = False
            for artist in artists:
                songs = [f for f in artist_to_files[artist] if f not in used]
                if not songs:
                    continue
                if playlist.count(artist) >= max_per_artist:
                    continue
                song = random.choice(songs)
                playlist.append(song)
                used.add(song)
                added_any = True
                # Count how many for this artist
                if playlist.count(song) >= max_per_artist:
                    break
                if len(playlist) >= n:
                    break
            if not added_any:
                break
        # If still not enough, fill up with any remaining songs
        if len(playlist) < n:
            leftovers = [f for f in filtered if f not in used]
            random.shuffle(leftovers)
            playlist.extend(leftovers[:n-len(playlist)])
        self.playlist = playlist[:n]
        self.playlist_box.delete(0, tk.END)
        for i, f in enumerate(self.playlist):
            try:
                tags = get_tags(f)
                title = tags.get('title') or os.path.basename(f)
                artist = tags.get('artist') or ''
                display = f"{i+1}. {title}"
                if artist:
                    display += f" - {artist}"
                self.playlist_box.insert(tk.END, display)
            except Exception:
                continue
        self.current = 0
        # Calculate total duration in minutes
        total_seconds = 0.0
        for f in self.playlist:
            try:
                tags = get_tags(f)
                # Try to get duration from tags
                audio = File(f)
                if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                    total_seconds += audio.info.length
            except Exception:
                continue
        total_minutes = int(total_seconds // 60)
        self.duration_label.config(text=f"Total duration: {total_minutes} min")
        if self.playlist:
            self.show_song(0)

    def shuffle_playlist(self):
        import random
        if not self.playlist:
            return
        random.shuffle(self.playlist)
        self.playlist_box.delete(0, tk.END)
        for i, f in enumerate(self.playlist):
            try:
                tags = get_tags(f)
                title = tags.get('title') or os.path.basename(f)
                artist = tags.get('artist') or ''
                display = f"{i+1}. {title}"
                if artist:
                    display += f" - {artist}"
                self.playlist_box.insert(tk.END, display)
            except Exception:
                continue
        self.current = 0
        if self.playlist:
            self.show_song(0)

    def on_select(self, event):
        if not self.playlist_box.curselection():
            return
        idx = self.playlist_box.curselection()[0]
        self.current = idx
        self.show_song(idx)
        self.play()

    def show_song(self, idx):
        f = self.playlist[idx]
        try:
            tags = self.tags_cache.get(f)
            if tags is None:
                tags = get_tags(f)
                self.tags_cache[f] = tags
        except Exception:
            tags = {}
        # Cover
        cover = tags.get('cover')
        if cover:
            try:
                image = Image.open(io.BytesIO(cover))
                image = image.resize((100,100))
                img = ImageTk.PhotoImage(image)
                self.cover_label.config(image=img)
                self.cover_label.image = img
            except Exception:
                self.cover_label.config(image='')
                self.cover_label.image = None
        else:
            # Draw a music note as fallback
            from PIL import ImageDraw, ImageFont
            img = Image.new('RGBA', (100, 100), (50, 54, 58, 255))
            draw = ImageDraw.Draw(img)
            # Try to use a system font with a music note
            try:
                font = ImageFont.truetype("seguisym.ttf", 72)
                note = "\u266B"
            except Exception:
                font = ImageFont.load_default()
                note = "♪"
            # Compute text size robustly for Pillow versions
            try:
                bbox = draw.textbbox((0, 0), note, font=font)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                try:
                    w, h = draw.textsize(note, font=font)
                except Exception:
                    w, h = font.getmask(note).size
            draw.text(((100-w)//2, (100-h)//2), note, font=font, fill=(184, 193, 236, 255))
            img_tk = ImageTk.PhotoImage(img)
            self.cover_label.config(image=img_tk)
            self.cover_label.image = img_tk
        # Song title under image
        # Always set a title even if tags are empty
        title = tags.get('title') or os.path.basename(f) or 'Unknown Title'
        artist = tags.get('artist') or ''
        # Split into two lines if both exist
        if artist and title:
            display_text = f"{title}\n{artist}"
        else:
            display_text = title or artist
        # Try to fit font size
        for size in (12, 10, 8):
            self.song_title_label.config(font=(self.FONT_FAMILY, size, "bold"), text=display_text)
            self.song_title_label.update_idletasks()
            # Get text width in pixels
            label_width = self.song_title_label.winfo_reqwidth()
            frame_width = self.cover_frame.winfo_width() or 300
            if label_width < frame_width - 10:
                break
        # Always center and wrap
        self.song_title_label.config(wraplength=frame_width-20, justify="center")

        # Reset progress bar
        self.progress_var.set(0)
        self.progress_bar['value'] = 0
        self.song_time_label.config(text="")
        # Lyrics
        lyrics = tags.get('lyrics') or tags.get('lyric')
        if not lyrics:
            lyrics = fetch_lyrics(tags.get('artist', ''), tags.get('title', ''))
        self.lyrics_text.delete(1.0, tk.END)
        # Normalize double linefeeds to single
        if lyrics:
            normalized_lyrics = lyrics.replace('\r\n', '\n').replace('\r', '\n')
            import re
            normalized_lyrics = re.sub(r'\n{2,}', '\n', normalized_lyrics)
        else:
            normalized_lyrics = "No lyrics found."
        self.lyrics_text.insert(tk.END, normalized_lyrics)

    def play(self):
        if not self.playlist:
            return
        f = self.playlist[self.current]
        if self.player:
            self.player.stop()
        self.player = vlc.MediaPlayer(f)
        # Set initial volume
        try:
            self.player.audio_set_volume(self.volume_var.get())
        except Exception:
            pass
        self.player.play()
        # Set play button to sunken
        if hasattr(self, 'play_btn'):
            self.play_btn.config(relief="sunken")
        self.update_progress_bar()


    def pause(self):
        if self.player:
            self.player.pause()
        # Set play button back to raised
        if hasattr(self, 'play_btn'):
            self.play_btn.config(relief="raised")
        # Optionally, do not update progress bar while paused


    def next(self):
        if not self.playlist:
            return
        self.current = (self.current + 1) % len(self.playlist)
        self.playlist_box.select_clear(0, tk.END)
        self.playlist_box.select_set(self.current)
        self.show_song(self.current)
        self.play()

    def prev(self):
        if not self.playlist:
            return
        self.current = (self.current - 1) % len(self.playlist)
        self.playlist_box.select_clear(0, tk.END)
        self.playlist_box.select_set(self.current)
        self.show_song(self.current)
        self.play()

    def clear_folders(self):
        self.folders = []
        save_selected_folders(self.folders)
        self.audio_files = []
        if hasattr(self, 'song_count_label'):
            self.song_count_label.config(text=f"Total songs: 0")
        self.genres = set()
        self.genre_vars = {}
        self.tags_cache = {}
        from persistence_utils import save_tags_cache
        save_tags_cache(self.tags_cache)
        self.update_folders_listbox()
        for widget in self.genre_frame.winfo_children():
            widget.destroy()
        self.playlist_box.delete(0, tk.END)
        self.duration_label.config(text="Total duration: 0 min")
        self.cover_label.config(image='')
        self.cover_label.image = None
        self.lyrics_text.delete(1.0, tk.END)

    def update_folders_listbox(self):
        self.folders_listbox.delete(0, tk.END)
        count = len(self.folders)
        self.selected_folders_label.config(text=f"Selected Folders ({count}):")
        if self.folders:
            for folder in self.folders:
                self.folders_listbox.insert(tk.END, folder)
        else:
            self.folders_listbox.insert(tk.END, "No folders selected.")

    def remove_selected_folders(self):
        selected_indices = list(self.folders_listbox.curselection())
        if not selected_indices:
            return
        # Remove from highest to lowest to avoid index shift
        for idx in reversed(selected_indices):
            if 0 <= idx < len(self.folders):
                del self.folders[idx]
        save_selected_folders(self.folders)
        self.update_folders_listbox()
        self.scan_files()

    def update_progress_bar(self):
        # Poll VLC for current position and update progress bar
        if not self.player:
            self.progress_var.set(0)
            self.progress_bar['value'] = 0
            self.song_time_label.config(text="")
            self._progress_animating = False
            return
        try:
            length = self.player.get_length() / 1000  # ms to seconds
            pos = self.player.get_time() / 1000
            if length > 0 and pos >= 0:
                percent = max(0, min(100, pos / length * 100))
                # Always animate from current visual value
                self._progress_last = self.progress_var.get()
                self._progress_next = percent
                self.progress_bar['maximum'] = 100
                # Format remaining time as -mm:ss
                remaining = max(0, length - pos)
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                self.song_time_label.config(text=f"-{mins}:{secs:02d}")
                self._progress_animating = True
                self.animate_progress_bar()
                # If song finished, move to next song
                if pos >= length - 0.5:
                    if self.playlist:
                        self.next()
                    else:
                        self.progress_var.set(0)
                        self.progress_bar['value'] = 0
                        self.song_time_label.config(text="")
                        self._progress_animating = False
                        self._progress_last = 0
                        self._progress_next = 0
                    return
            else:
                self.progress_var.set(0)
                self.song_time_label.config(text="")
                self._progress_animating = False
            # Poll again for new values every 500ms
            self.root.after(500, self.update_progress_bar)
        except Exception:
            self.song_time_label.config(text="")
            self.root.after(1000, self.update_progress_bar)

    def animate_progress_bar(self):
        # Animate smoothly between _progress_last and _progress_next
        if self._progress_dragging:
            return  # Don't animate while dragging
        if not getattr(self, '_progress_animating', False):
            return
        last = getattr(self, '_progress_last', 0)
        next_ = getattr(self, '_progress_next', 0)
        steps = 16  # About 500ms/16 = 31ms per step
        diff = (next_ - last) / steps
        def step(i=1, val=last):
            if self._progress_dragging:
                return
            if not getattr(self, '_progress_animating', False):
                return
            val += diff
            self.progress_var.set(max(0, min(100, val)))
            if i < steps:
                self.root.after(31, step, i+1, val)
            else:
                self._progress_last = next_
        step()

    def on_progress_click(self, event):
        # Seek to position on click
        self._progress_dragging = True
        self.seek_progress(event)

    def on_progress_drag(self, event):
        # Seek to position while dragging
        self._progress_dragging = True
        self.seek_progress(event)

    def on_progress_release(self, event):
        # Seek to position and resume animation
        self.seek_progress(event)
        self._progress_dragging = False
        self.animate_progress_bar()

    def seek_progress(self, event):
        # Calculate seek position and set VLC time
        if not self.player:
            return
        bar = self.progress_bar
        length = self.player.get_length() / 1000  # seconds
        if length <= 0:
            return
        x = event.x
        w = bar.winfo_width()
        percent = max(0, min(1, x / w))
        new_time = int(percent * length * 1000)  # ms
        self.player.set_time(new_time)
        self.progress_var.set(percent * 100)
        # Optionally, show tooltip or update duration label with current time
        # Show remaining time as -mm:ss
        current = percent * length
        remaining = max(0, length - current)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        self.song_time_label.config(text=f"-{mins}:{secs:02d}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PlayerApp(root)
    root.mainloop()
