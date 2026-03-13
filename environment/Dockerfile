FROM node:20-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    docker-compose \
    docker.io \
    git \
    postgresql \
    postgresql-client \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN chmod +x scripts/init-postgres.sh
RUN npm install --no-audit --no-fund
