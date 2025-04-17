import pickle
import os
import re
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

def migrate_tags_cache(cache_path):
    if not os.path.exists(cache_path):
        print(f"Cache file not found: {cache_path}")
        return
    with open(cache_path, 'rb') as f:
        tags_cache = pickle.load(f)
    changed = False
    for filepath, tags in tags_cache.items():
        # Only add 'genres' if missing or incorrect
        genre_str = tags.get('genre', '')
        # Always re-parse and overwrite the 'genres' field
        split_genres = re.split(r'[;|,/\\>\-]+', genre_str)
        split_genres = [g.strip() for g in split_genres if g.strip()]
        if tags.get('genres') != split_genres:
            tags['genres'] = split_genres
            changed = True
    if changed:
        with open(cache_path, 'wb') as f:
            pickle.dump(tags_cache, f)
        print("Migration complete: genres field added to all entries.")
    else:
        print("No migration needed: all entries already have genres field.")

if __name__ == "__main__":
    # Adjust the path if needed
    cache_file = os.path.join(os.path.dirname(__file__), 'tags_cache.pkl')
    migrate_tags_cache(cache_file)
