import os
import json
import pickle

FOLDERS_FILE = os.path.join(os.path.dirname(__file__), 'selected_folders.json')
TAGS_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'tags_cache.pkl')

def save_selected_folders(folders):
    try:
        with open(FOLDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(folders, f)
    except Exception:
        pass

def load_selected_folders():
    try:
        if os.path.exists(FOLDERS_FILE):
            with open(FOLDERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_tags_cache(tags_cache):
    try:
        with open(TAGS_CACHE_FILE, 'wb') as f:
            pickle.dump(tags_cache, f)
    except Exception:
        pass

def load_tags_cache():
    try:
        if os.path.exists(TAGS_CACHE_FILE):
            with open(TAGS_CACHE_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception:
        pass
    return {}
