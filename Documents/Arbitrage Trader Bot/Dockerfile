FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data directory for SQLite DB and logs
RUN mkdir -p data

ENV PYTHONUNBUFFERED=1

CMD ["python", "src/bot.py", "--paper"]
