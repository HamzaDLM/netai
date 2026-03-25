FROM rust:1.85-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends pkg-config libssl-dev libsasl2-dev zlib1g-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN cargo build --release

CMD ["./target/release/log_ingestor"]
