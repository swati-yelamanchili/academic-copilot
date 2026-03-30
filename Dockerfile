FROM python:3.11-slim

# Install system dependencies (needed by Playwright and other general utilities)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and root OS dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy app code
COPY . .

# Expose Render port
EXPOSE 5000

# Start server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "600", "--workers", "2", "main:app"]
