FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Hugging Face Spaces assigns a dynamic port via the PORT environment variable (default 7860)
# Our Python script naturally uses `os.environ.get("PORT", 8000)` so it handles this perfectly!
CMD ["python", "main.py"]
