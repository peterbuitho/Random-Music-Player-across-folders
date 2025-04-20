# Random Music Player (Desktop Edition)

A modern desktop application with a beautiful UI for browsing, filtering, and playing your music library across multiple folders, built with Python and Tkinter.
Check out the [Gradio version](music_player_gradio/README.md) for a web-based experience.

## Features

- 🎵 Browse and play music from multiple folder locations
- 🎸 Filter songs by genre
- 🎮 Native desktop player with progress visualization
- 🔄 Automatic playlist generation
- 🎨 Modern and responsive UI elements
- 🔎 Smart song organization and filtering
- 💾 Persistent configuration with saved folders and preferences
- 🔗 OpenRouter AI integration for model selection with free tier options
- 📝 Lyrics display (when available)
- 🖼️ Album cover support

## Installation

### Requirements

```
Python 3.8+
tkinter (included with Python)
python-vlc
mutagen
Pillow
requests
rapidfuzz (only for Gradio version)
```

Install dependencies using pip:

```bash
pip install -r requirements.txt
```

### VLC Media Player

This application requires VLC Media Player to be installed on your system:
1. Download and install VLC from [videolan.org](https://www.videolan.org/)
2. Ensure VLC is in your system PATH

### Configuration

1. On first launch, you'll be prompted to select your music folders
2. The application will save your selected folders for future sessions
3. (Optional) Set up an OpenRouter API key for AI model selection

## Running the Application

Start the application by running:

```bash
python music_player.py
```

## Using the Desktop Player

### Music Library Management

- **Add Folders**: Click the "Select Folders" button to add music folders
- **Remove Folders**: Select a folder and click "Remove Selected"
- **Clear All**: Click "Clear All" to remove all folders

### Playback Controls

- **Play/Pause**: Toggle playback of the current song
- **Next/Previous**: Move to the next or previous song in the playlist
- **Shuffle**: Create a new random playlist with the selected genres
- **Progress Bar**: Click or drag to seek to a specific position in the song

### Genre Filtering

- Use the genre checkboxes to filter songs by genre
- The count of available songs updates automatically based on your selection

## OpenRouter AI Integration

The player includes integration with OpenRouter for AI model selection:

- View available AI models from OpenRouter
- Filter to show only free/included models
- Display pricing information for each model
- Save model preferences for future use
- Refresh to get the latest available models

## Code Structure

- `music_player.py`: Main application file
- `persistence_utils.py`: Utilities for saving/loading application state
- `requirements.txt`: Python dependencies

## Building a Standalone Executable

This application can be packaged into a standalone executable using PyInstaller:

```bash
pip install pyinstaller
pyinstaller pyinstaller.spec
```

The executable will be created in the `dist` folder.

## License

MIT License
