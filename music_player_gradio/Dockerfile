FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Gradio/FastAPI port
EXPOSE 7860

# Run Uvicorn server
CMD ["uvicorn", "music_player_gradio:app", "--host", "0.0.0.0", "--port", "7860"]
