FROM node:22-alpine AS frontend-build
WORKDIR /opt/pinky-bread/frontend
COPY frontend/package.json ./package.json
COPY frontend/tsconfig.json ./tsconfig.json
COPY frontend/vite.config.ts ./vite.config.ts
COPY frontend/src ./src
RUN npm install --no-audit --no-fund && npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /opt/pinky-bread
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY config ./config
COPY web ./web
COPY --from=frontend-build /opt/pinky-bread/web/app ./web/app
COPY run.py ./run.py
RUN mkdir -p data/uploads && useradd --create-home --uid 10001 pinky_bread && chown -R pinky_bread:pinky_bread /opt/pinky-bread
USER pinky_bread
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
