# Salim — Supermarket Price Pipeline

Fetches supermarket price publications, pipes them through a queue, and
serves the normalized data over an API.

[מאגר מחירי סופרים ממשלתי](https://www.gov.il/he/pages/cpfta_prices_regulations)

## Architecture

The extractor trigger strategy is documented in
[`docs/decisions/0001-triggering-extractors.md`](../docs/decisions/0001-triggering-extractors.md):
the worker polls S3 every three hours and processes only each store's delta.

```
crawler (cron) --> Supabase Storage bucket (zip files)
                        |
                        v
              extractor worker (3-hour S3 delta poll)
                        |
                        v
                  RabbitMQ (CloudAMQP)
                        |
                        v
              loader worker (format, upsert into DB)
                        |
                        v
                Supabase Postgres
                        |
                        v
                  FastAPI (api service)
```

| Stage       | Local dev (docker-compose) | Production            |
|-------------|-----------------------------|------------------------|
| Object store | MinIO (S3-compatible)      | Supabase Storage       |
| Queue        | RabbitMQ                   | CloudAMQP              |
| Database     | Postgres                   | Supabase Postgres      |
| Compute      | docker-compose services     | Python worker platform |

Each service reads its object store / queue / DB connection details from
environment variables, so the same code runs locally against MinIO/RabbitMQ/Postgres
and in production against Supabase Storage/CloudAMQP/Supabase Postgres —
only the `.env` values change.

## Folder structure

```
salim/
  docker-compose.yml       # full local stack: infra + all 4 services
  .env.example             # copy to .env and fill in
  shared/                  # code shared by loader + api (DB models, engine)
  crawler/                 # scrapes source site, zips output, uploads to bucket
  services/
    extractor/             # pulls zip from bucket, extracts, converts to JSON, publishes to queue
    loader/                # consumes queue, formats, writes to DB
  api/                     # FastAPI read API over the stored data
```

## Running locally

```bash
cd salim
cp .env.example .env
docker compose up --build
```

- MinIO console: http://localhost:9001 (user/pass from `.env`)
- RabbitMQ management UI: http://localhost:15672
- API docs: http://localhost:8000/docs

## Services

- **crawler** — runs on an internal schedule (`CRON_SCHEDULE` env, cron syntax),
  scrapes/downloads source price files, zips them, and uploads the zip to the
  `raw-prices` bucket.
- **extractor worker** — every three hours, paginates through `SalimPrices`,
  downloads only objects above each store's watermark, runs
  `prices.py`/`promotions.py`, and publishes persistent JSON messages to
  `raw-prices`. It records `<store>_extractor_last_poll_time` as a JSON object
  in S3 only after RabbitMQ confirms all messages. Source objects are retained.
- **loader** — consumes the `raw-prices` queue, normalizes/validates each message,
  and upserts it into the `prices` table (plus `stores`/`products` lookup tables).
- **api** — FastAPI service exposing read endpoints over the `prices` data.

## Deploying to production

For local worker verification:

```bash
cd salim
docker compose up --build rabbitmq minio extractor
```

The worker reads RabbitMQ credentials from `services/.env` when present. Set
`EXTRACTOR_POLL_INTERVAL_SECONDS` to a smaller value for local iteration; the
production default is `10800` seconds (three hours).

### GitHub Actions schedule

`.github/workflows/salim-extractor.yml` runs a single poll every six hours and
can also be started manually. The first run for a store is a full backfill
because `<store>_extractor_last_poll_time` does not exist yet. Later runs read
that checkpoint, process through the poll's start time, and update it only
after RabbitMQ confirms the messages.

Add these repository **Actions secrets**:

- `SUPABASE_ACCESS_SECRET_KEY`
- `S3_ENDPOINT_URL`
- `RABBITMQ_URL`

Add these repository **Actions variables**:

- `SUPABASE_ACCESS_KEY_ID`

Optional repository **Actions variables** (defaults shown):

- `S3_BUCKET=SalimPrices`
- `S3_REGION=us-east-1`
- `RABBITMQ_QUEUE=raw-prices`
- `EXTRACTOR_BATCH_SIZE=30`
