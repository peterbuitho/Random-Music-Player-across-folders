import os
import json
from pathlib import Path
import requests

CONFIG_DIR = "config"
API_KEY_FILE = os.path.join(CONFIG_DIR, "openrouter_api_key.json")

# Default model to use if none is specified
DEFAULT_MODEL = "openai/gpt-3.5-turbo"

# Popular free or low-cost models
FREE_MODELS = [
    {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "description": "Fast and efficient model with good quality responses"},
    {"id": "anthropic/claude-instant-1", "name": "Claude Instant", "description": "Quick responses with good quality"},
    {"id": "google/gemini-pro", "name": "Gemini Pro", "description": "Google's capable general-purpose model"},
    {"id": "meta-llama/llama-3-8b-instruct", "name": "Llama 3 (8B)", "description": "Meta's latest smaller but capable model"},
    {"id": "mistralai/mistral-7b-instruct", "name": "Mistral 7B", "description": "Efficient open model with good performance"},
    {"id": "cohere/command-r", "name": "Cohere Command-R", "description": "Specialized in task execution"},
]

def save_api_key(api_key, model_id=None):
    """Save OpenRouter API key and selected model to a config file"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # First load existing config if any
    config = {}
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass
    
    # Update with new values
    config["api_key"] = api_key
    if model_id:
        config["model_id"] = model_id
    
    # Save back to file
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f)
    
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

def load_selected_model():
    """Load the selected model ID from config file
    
    Returns: The saved model ID from the config file, or DEFAULT_MODEL if not found
    """
    # Make sure CONFIG_DIR exists
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    if not os.path.exists(API_KEY_FILE):
        print(f"Config file not found at {API_KEY_FILE}, using default model: {DEFAULT_MODEL}")
        return DEFAULT_MODEL
    
    try:
        with open(API_KEY_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            saved_model = config.get("model_id")
            
            if saved_model:
                print(f"Loaded saved model preference: {saved_model}")
                return saved_model
            else:
                print(f"No model preference found in config, using default: {DEFAULT_MODEL}")
                return DEFAULT_MODEL
    except Exception as e:
        print(f"Error loading model preference: {e}, using default: {DEFAULT_MODEL}")
        return DEFAULT_MODEL

def save_selected_model(model_id):
    """Save the selected model ID to config file"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # First load existing config
    config = {}
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass
    
    # Update model ID
    config["model_id"] = model_id
    
    # Save back to file
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f)
    
    return True

def get_available_models(include_free_only=False):
    """Get a list of available models from OpenRouter API
    
    Args:
        include_free_only: If True, only include models that have 'free' in their name or description
    
    Returns:
        List of models in the format [{'id': 'model_id', 'name': 'Model Name', 'description': '...'}]
        sorted by latency (lowest/fastest first)
    """
    # First try to fetch from the API
    api_key = load_api_key()
    if not api_key:
        # Return predefined list with estimated latency values
        for model in FREE_MODELS:
            if "latency" not in model:
                # Add estimated latency based on model size
                if "3.5" in model["id"] or "instant" in model["id"].lower():
                    model["latency"] = 1.0  # Faster models
                elif "7b" in model["id"].lower() or "8b" in model["id"].lower():
                    model["latency"] = 2.0  # Medium-sized models
                else:
                    model["latency"] = 3.0  # Larger models
        
        # Sort by estimated latency
        return sorted(FREE_MODELS, key=lambda x: x.get("latency", 999))
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://music-player-gradio.app",
            "X-Title": "Music Player Gradio"
        }
        
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers
        )
        
        response.raise_for_status()
        models_data = response.json()
        
        # Process and format the models
        models = []
        for model in models_data.get("data", []):
            model_id = model.get("id")
            model_name = model.get("name", model_id)
            model_description = model.get("description", "")
            context_length = model.get("context_length", 0)
            pricing = model.get("pricing", {})
            
            # Extract latency information where available
            # OpenRouter might provide different metrics, look for all possible ones
            latency = 999  # Default high value for sorting
            
            # Check various possible latency fields in the API response
            if "latency" in model:
                latency = model["latency"]
            elif "performance" in model and "latency" in model["performance"]:
                latency = model["performance"]["latency"]
            elif "benchmark" in model and "latency" in model["benchmark"]:
                latency = model["benchmark"]["latency"]
            else:
                # Estimate latency based on model name patterns
                if "3.5" in model_id or "instant" in model_id.lower() or "small" in model_id.lower():
                    latency = 1.0  # Faster models
                elif any(size in model_id.lower() for size in ["7b", "8b", "tiny", "mini"]):
                    latency = 2.0  # Medium-sized models
                elif any(size in model_id.lower() for size in ["13b", "14b", "medium"]):
                    latency = 3.0  # Larger models
                elif any(size in model_id.lower() for size in ["70b", "llama-2", "large"]):
                    latency = 4.0  # Very large models
            
            # Skip if we only want free models and this doesn't match
            if include_free_only:
                # Look for 'free' in various fields
                model_text = (model_name + model_description + str(pricing)).lower()
                if 'free' not in model_text:
                    continue
            
            # Format for our UI
            models.append({
                "id": model_id,
                "name": model_name,
                "description": model_description,
                "context_length": context_length,
                "pricing": pricing,
                "latency": latency
            })
        
        # Sort by latency (lowest first)
        sorted_models = sorted(models, key=lambda x: x.get("latency", 999))
        
        # If we got models, return them
        if sorted_models:
            return sorted_models
            
        # Otherwise fall back to the predefined list
        for model in FREE_MODELS:
            if "latency" not in model:
                # Add estimated latency
                if "3.5" in model["id"] or "instant" in model["id"].lower():
                    model["latency"] = 1.0
                elif "7b" in model["id"].lower() or "8b" in model["id"].lower():
                    model["latency"] = 2.0
                else:
                    model["latency"] = 3.0
        
        return sorted(FREE_MODELS, key=lambda x: x.get("latency", 999))
        
    except Exception as e:
        print(f"Error fetching models from OpenRouter: {e}")
        # Fall back to the predefined list
        return FREE_MODELS

def chat_completion(messages, model=None):
    """Get a chat completion from OpenRouter API"""
    api_key = load_api_key()
    if not api_key:
        return {"error": "No API key found. Please add your OpenRouter API key in settings."}
    
    # If model is not provided, use the saved preference or default
    if not model:
        model = load_selected_model()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://music-player-gradio.app",  # Required by OpenRouter
        "X-Title": "Music Player Gradio"  # Helps OpenRouter track usage
    }
    
    data = {
        "model": model,
        "messages": messages
    }
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            # Add timeout to prevent hanging connections
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30  # 30 second timeout
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.ConnectionError as e:
            # Handle connection reset errors specifically
            if attempt < max_retries - 1:
                # Wait before retrying with exponential backoff
                import time
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                continue
            else:
                return {"error": f"Connection error after {max_retries} attempts: {str(e)}"}
                
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay * (2 ** attempt))
                continue
            else:
                return {"error": "Request timed out after multiple attempts"}
                
        except Exception as e:
            return {"error": f"API request failed: {str(e)}"}

def parse_genre_request(query, available_genres):
    """
    Parse a user request to filter by genres, duration, and year range, and pick songs
    
    Returns:
    - selected_genres: list of selected genres
    - num_songs: number of songs to pick (or None if not specified)
    - duration: target duration in minutes (or None if not specified)
    - year_start: start year (or None if not specified)
    - year_end: end year (or None if not specified)
    - title_keywords: list of keywords to match in song titles (or None if not specified)
    - album_filters: list of album names to filter by (or None if not specified)
    - error: error message if any
    """
    messages = [
        {"role": "system", "content": f"You are a helpful assistant that helps users filter music by genre, duration, year range, track title keywords, album names, and artist names. Available genres are: {', '.join(available_genres)}. Identify which genres the user wants, the number of songs or target duration, optional start/end years, keywords to match in song titles, album filters, and artist filters (artist names)."},
        {"role": "user", "content": query}
    ]
    
    response = chat_completion(messages)
    
    if "error" in response:
        return [], None, None, None, None, None, None, response["error"]
    
    try:
        assistant_message = response["choices"][0]["message"]["content"]
        
        # Now ask the model to parse its own response into a structured format
        parsing_messages = [
            {"role": "system", "content": "Extract genres, song count (if specified), target duration (minutes), optional year_start, year_end, list of title keywords (title_keywords), list of album names (album_filters), and list of artist names (artist_filters) from your previous response. Return JSON in this format: {\"genres\": [\"pop\"], \"count\": 5, \"duration\": 20, \"year_start\": 1980, \"year_end\": 1990, \"title_keywords\": [\"summer\"], \"album_filters\": [\"Summer Hits\"], \"artist_filters\": [\"ABBA\"]}. Omit any fields not specified by the user."},
            {"role": "user", "content": f"Available genres: {', '.join(available_genres)}\nYour response: {assistant_message}\n\nExtract as JSON:"}
        ]
        
        parsing_response = chat_completion(parsing_messages)
        
        if "error" in parsing_response:
            return [], None, None, None, None, None, None, parsing_response["error"]
        
        parsed_content = parsing_response["choices"][0]["message"]["content"]
        
        # Extract JSON from the response (handle cases where there's text around the JSON)
        import re
        json_match = re.search(r'({.*})', parsed_content, re.DOTALL)
        if json_match:
            try:
                parsed_json = json.loads(json_match.group(1))
                
                selected_genres = [g for g in parsed_json.get("genres", []) if g in available_genres]
                
                # Safely parse count, avoid int(None)
                raw_count = parsed_json.get("count", None)
                try:
                    if raw_count is not None:
                        num_songs = int(raw_count)
                        if num_songs <= 0:
                            num_songs = None
                        elif num_songs > 100:
                            num_songs = 100
                    else:
                        num_songs = None
                except Exception:
                    num_songs = None
                
                duration = parsed_json.get("duration", None)
                year_start = parsed_json.get("year_start", None)
                year_end = parsed_json.get("year_end", None)
                title_keywords = parsed_json.get("title_keywords", None)
                album_filters = parsed_json.get("album_filters", None)
                artist_filters = parsed_json.get("artist_filters", None)
                
                # Normalize year values
                try:
                    year_start = int(year_start) if year_start else None
                    year_end = int(year_end) if year_end else None
                except:
                    year_start = year_end = None

                # --- Fallback: parse decade expressions from user query if LLM failed ---
                if (year_start is None and year_end is None):
                    import re
                    # Look for decade pattern: e.g. 2020s, 2020's, the 1980s, etc.
                    decade_match = re.search(r"(\d{4})['’]?s", query)
                    if decade_match:
                        decade = int(decade_match.group(1))
                        year_start = decade
                        year_end = decade + 9
                    else:
                        # If a precise year is mentioned (not followed by 's'), do not interpret as decade
                        year_match = re.search(r"\b(\d{4})\b", query)
                        if year_match:
                            year = int(year_match.group(1))
                            year_start = year
                            year_end = year
                
                return selected_genres, num_songs, duration, year_start, year_end, title_keywords, album_filters, artist_filters, None
            except Exception as e:
                return [], None, None, None, None, None, None, None, f"Failed to parse response: {str(e)}"
        
        return [], None, None, None, None, None, None, None, "Could not extract valid genres and filters"
        
    except Exception as e:
        return [], None, None, None, None, None, None, None, f"Failed to process response: {str(e)}"
