FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

RUN playwright install --with-deps chromium

COPY . .

ENV DISPLAY=:99

CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x800x24 & python main.py"]
