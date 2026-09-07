# APIx — one image: API, dashboard, operator console and the daily scheduler.
FROM python:3.12-slim

# Chromium's runtime libraries. Playwright downloads the browser itself; these
# are the shared objects it links against, and without them it fails at launch
# with an error that does not mention the missing library.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates fonts-liberation libnss3 libnspr4 libatk1.0-0 \
      libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
      libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY . .

# The database and the raw archive live on a mounted volume, not in the image.
# An airfare cannot be collected retrospectively, so a redeploy that wiped the
# archive would destroy days that can never be recovered.
ENV APIX_DB_PATH=/data/apix.db
VOLUME ["/data"]

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn webapp.backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
