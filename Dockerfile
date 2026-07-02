# Use an official lightweight Python image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies, especially FFmpeg which is required for voice/audio support
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY bot.py .
COPY database.py .
COPY cogs/ ./cogs/

# Create folders for persistent storage (SQLite DB and custom sound files)
RUN mkdir -p /app/sounds

# Declare volume paths for local data persistence
VOLUME [ "/app/sounds", "/app/data" ]

# We'll configure our database to be stored in the persistent volume
ENV DATABASE_PATH=/app/data/bot.db

# Run the application
CMD ["python", "bot.py"]
