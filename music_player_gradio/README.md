# Random Music Player (Gradio Web Edition)

A modern web-based music player application with a beautiful UI, built with Python, FastAPI, and Gradio. It provides a responsive interface for browsing, filtering, and playing your music library across multiple folders.

## Features

- 🎵 Browse and play music from multiple folder locations
- 🎸 Filter songs by genre
- 🎮 Web-based player with waveform visualization
- 🔄 Automatic playlist generation
- 🧠 AI-powered playlist creation using natural language
- 🎨 Light and dark theme support
- 📱 Responsive design for desktop and mobile
- 🔎 Fuzzy matching for search queries
- 🔗 OpenRouter AI integration for conversational music requests
- 📊 Direct access to music files and metadata via REST API

## Installation

### Requirements

```
Python 3.8+
FastAPI
Gradio 3.x+
Mutagen
```

Install dependencies using pip:

```bash
pip install -r requirements.txt
```

### Configuration

1. Create a folder for your music files
2. Configure the application by setting your music paths
3. (Optional) Set up an OpenRouter API key for AI chat functionality

## Running the Application

### Standard Method

Start the server with:

```bash
uvicorn music_player_gradio:app --host 0.0.0.0 --port 7860
```

Then open your browser to `http://localhost:7860/web` to access the web interface.

### Docker Deployment

The application includes Docker support for easy containerization and deployment.

#### Using docker-compose (Recommended)

1. Configure your music folder path in `docker-compose.yml`:
   ```yaml
   volumes:
     - "/path/to/your/music:/app/music:ro"  # Replace with your music folder path
     - "./cache:/app/cache"
   ```

2. Set your OpenRouter API key (for AI features) as an environment variable:
   ```bash
   export OPENROUTER_API_KEY=your_api_key_here
   ```

3. Build and start the container:
   ```bash
   docker-compose up -d
   ```

4. Access the web interface at `http://localhost:7860/web`

#### Manual Docker Build

Alternatively, you can build and run the Docker container manually:

```bash
# Build the image
docker build -t music-player-gradio .

# Run the container
docker run -p 7860:7860 \
  -v "/path/to/your/music:/app/music:ro" \
  -v "./cache:/app/cache" \
  -e OPENROUTER_API_KEY=your_api_key_here \
  music-player-gradio
```

## API Documentation

The application exposes the following REST API endpoints for direct integration:

### Playlist API

#### GET `/playlist`

Returns the current playlist with all song metadata.

**Query Parameters:**
- `new_playlist`: (boolean) Generate a new random playlist if set to `1` or `true`
- `force_refresh`: (boolean) Force a refresh of the playlist cache
- `ts`: (timestamp) Cache-busting parameter

**Response:**
```json
{
  "playlist": [
    {
      "index": 0,
      "title": "Song Title",
      "artist": "Artist Name",
      "album": "Album Name",
      "year": 2023,
      "genres": ["Rock", "Alternative"],
      "audio_url": "/audio/0?cache=1234567890",
      "lyrics_url": "/lyrics/0",
      "cover_url": "/cover/0"
    }
  ],
  "autoplay": true,
  "current": 0,
  "signature": "unique-playlist-signature"
}
```

#### POST `/pick_songs`

Generate a new random playlist with optional filters.

**Request Body:**
```json
{
  "count": 10,
  "genres": ["Rock", "Jazz"]
}
```

**Response:** Same format as the `/playlist` endpoint

### Media APIs

#### GET `/audio/{idx}`

Stream an audio file from the playlist by its index.

**URL Parameters:**
- `idx`: The index of the song in the playlist

**Response:**
- Audio file stream with appropriate content type
- Status 404 if song not found
- Status 500 on server error

#### GET `/lyrics/{idx}`

Get lyrics for a song in the playlist.

**URL Parameters:**
- `idx`: The index of the song in the playlist

**Response:**
```json
{
  "lyrics": "Song lyrics text..."
}
```

#### GET `/cover/{idx}`

Get album cover art for a song in the playlist.

**URL Parameters:**
- `idx`: The index of the song in the playlist

**Response:**
- Image file with appropriate content type
- Status 404 if cover art not found

### Utility APIs

#### GET `/direct-refresh-playlist`

Refreshes the player page with the current playlist.

**Query Parameters:**
- `autoplay`: (boolean) Whether to start playing automatically (default: true)
- `api`: The API source requesting the refresh (default: "web")

**Response:**
- HTML redirect to the player page

## Advanced Features

### OpenRouter AI Integration

The player includes integration with OpenRouter for AI-powered music selection. You can request specific songs, genres, or moods using natural language.

Example phrases:
- "Play 5 random jazz songs"
- "I want to listen to some rock and metal music"
- "Create a playlist with 15 classical and ambient songs"
- "Pick some electronic tracks"

### Year Filtering

Filter songs by release year:
- By specific year
- By year range (e.g., 1980-1990)

### Cover Art Support

The application automatically detects album cover art:
- From folder.jpg/png or cover.jpg/png in the same directory as audio files
- Support for embedded cover art in audio files

## Code Structure

- `music_player_gradio.py`: Main application file
- `openrouter_utils.py`: OpenRouter AI integration utilities
- `static/player.html`: Web-based player interface
- `requirements.txt`: Python dependencies

## License

MIT License
