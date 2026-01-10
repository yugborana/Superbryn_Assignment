FROM python:3.11-slim-bookworm

# Install system dependencies (needed for audio processing)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency file
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your actual code
COPY . . 


# Run the agent
CMD ["python", "main.py", "start"]