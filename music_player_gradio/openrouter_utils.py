import os
import json
from pathlib import Path
import requests

CONFIG_DIR = "config"
API_KEY_FILE = os.path.join(CONFIG_DIR, "openrouter_api_key.json")

def save_api_key(api_key):
    """Save OpenRouter API key to a config file"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_key": api_key}, f)
    
    return True

def load_api_key():
    """Load OpenRouter API key from config file"""
    if not os.path.exists(API_KEY_FILE):
        return None
    
    try:
        with open(API_KEY_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("api_key")
    except Exception as e:
        print(f"Error loading API key: {e}")
        return None

def chat_completion(messages, model="meta-llama/llama-3-8b-instruct"):
    """Get a chat completion from OpenRouter API"""
    api_key = load_api_key()
    if not api_key:
        return {"error": "No API key found. Please add your OpenRouter API key in settings."}
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": messages
    }
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )
        
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"API request failed: {str(e)}"}

def parse_genre_request(query, available_genres):
    """
    Parse a user request to filter by genres and pick songs
    
    Returns:
    - selected_genres: list of selected genres
    - num_songs: number of songs to pick
    - error: error message if any
    """
    messages = [
        {"role": "system", "content": f"You are a helpful assistant that helps users filter music by genre and pick songs. Available genres are: {', '.join(available_genres)}. Your task is to identify which genres the user wants and how many songs they want to pick."},
        {"role": "user", "content": query}
    ]
    
    response = chat_completion(messages)
    
    if "error" in response:
        return [], 10, response["error"]
    
    try:
        assistant_message = response["choices"][0]["message"]["content"]
        
        # Now ask the model to parse its own response into a structured format
        parsing_messages = [
            {"role": "system", "content": "Extract the genres and song count from your previous response. Return JSON in the format: {\"genres\": [\"genre1\", \"genre2\"], \"count\": 10}. Only include genres from the available list."},
            {"role": "user", "content": f"Available genres: {', '.join(available_genres)}\nYour response: {assistant_message}\n\nExtract genres and song count as JSON:"}
        ]
        
        parsing_response = chat_completion(parsing_messages)
        
        if "error" in parsing_response:
            return [], 10, parsing_response["error"]
        
        parsed_content = parsing_response["choices"][0]["message"]["content"]
        
        # Extract JSON from the response (handle cases where there's text around the JSON)
        import re
        json_match = re.search(r'({.*})', parsed_content, re.DOTALL)
        if json_match:
            try:
                parsed_json = json.loads(json_match.group(1))
                
                # Validate and filter genres
                selected_genres = [g for g in parsed_json.get("genres", []) if g in available_genres]
                num_songs = int(parsed_json.get("count", 10))
                
                # Ensure reasonable number of songs
                if num_songs <= 0:
                    num_songs = 10
                elif num_songs > 100:
                    num_songs = 100
                    
                return selected_genres, num_songs, None
            except Exception as e:
                return [], 10, f"Failed to parse response: {str(e)}"
        
        return [], 10, "Could not extract valid genres and song count"
        
    except Exception as e:
        return [], 10, f"Failed to process response: {str(e)}"
