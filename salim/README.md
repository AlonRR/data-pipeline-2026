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
- **loader** — consumes `raw-prices` in batches, upserts price items into
  `products` + `prices` and promotions into `promotions` + `promotion_items`,
  and fills in each product's manufacturer. See
  [Loader and enricher](#loader-and-enricher).
- **api** — FastAPI service exposing read endpoints over the `prices` data.

## Loader and enricher

The loader (`services/loader/`) is the queue consumer.
Both extractor outputs land on the same `raw-prices` queue, so each message is dispatched by shape:
a `promotionId` means a promotion, `itemCode` + `price` means a price item, anything else is poison.

**Tables.**
They are created with `create_all()` at startup.
There is no migration tool yet, so a column change on a live database is a manual `ALTER`.

| Table | Key | Holds |
|---|---|---|
| `chains` | `chain_id` | ChainId → display name, seeded from `chains.py` |
| `products` | `(provider, item_code)` | name, unit fields, and the manufacturer with its `manufacturer_status` (`pending` / `resolved` / `unknown`) |
| `prices` | `(provider, store_id, item_code)` | current price and the source `update_time` |
| `promotions` | `(provider, store_id, promotion_id)` | description and validity window |
| `promotion_items` | `(…, item_code)` | per-item deal terms; replaced wholesale when the promotion is upserted |
| `manufacturers` | normalized item name | resolution cache and audit log (`source` is `dictionary`, `llm` or `manual`) |

`provider` is the numeric `ChainId` from the XML, everywhere.
Every write is an idempotent upsert, and a row's `update_time` never goes backwards, so redelivered or out-of-order messages are harmless.
Poison messages are copied to `raw-prices.dlq` (with an `x-reason` header) and acked; anything else that fails nacks the whole batch back for redelivery.
All tables have row-level security enabled without public Data API policies;
the backend services use the privileged Postgres connection directly.

**Manufacturer enrichment** runs in two tiers.
The consumer only does what costs nothing, in order: the XML's own `ManufactureName` (unless it is a placeholder like `לא ידוע`) → the `manufacturers` cache → a whole-token match against the seed brand dictionary (`brands.py`; a name mentioning two brands is treated as ambiguous).
Whatever falls through stays `pending`.
The consumer reloads the cache every `LOADER_CACHE_REFRESH_SECONDS` (default 10 minutes) to pick up what the sweeper resolved.
The sweeper, `enrich.py --backfill`, then sends pending names to `claude-haiku-4-5` in batches of 50 with a structured-output schema, marks each product `resolved` or `unknown`, and caches the answer so the same name is never asked twice, on any chain.
It exits immediately when nothing is pending, and a failed request charges every name in that batch one attempt and ends the run (`ENRICHER_MAX_ATTEMPTS`, default 3), so an outage costs one request per run.

```bash
docker compose run --rm loader-enrich                       # resolve pending products
docker compose run --rm loader-enrich python enrich.py --reset-attempts   # retry exhausted names
docker compose run --rm loader-enrich python enrich.py --reset-unknown    # re-ask "no manufacturer" answers
```

Set `ANTHROPIC_API_KEY` in `.env`; the model is `ENRICHER_MODEL`.
In production run the same command on a schedule (hourly is plenty).

The LLM is deliberately a thin seam.
`enrich.py` builds one `anthropic.Anthropic()` client and calls `messages.create` with a system prompt, a JSON list of `{id, name}` and a JSON schema for the answer; nothing else about the pipeline knows a model exists.
To change the model, set `ENRICHER_MODEL`.
To point at another endpoint that speaks the Anthropic Messages API (a proxy, or a local server that emulates it), set `ANTHROPIC_BASE_URL`; the SDK reads it without code changes.
To swap providers entirely, implement the two-line `Resolver` protocol in `enrich.py` (`model` attribute plus `resolve(batch) -> {id: manufacturer | None}`) and hand it to `run_backfill`; the tests use exactly that hook with a fake.
The API is billed from Console credits, separately from a claude.ai subscription; the key alone is not enough.

## Deploying to production

Each of `crawler/`, `services/extractor/`, `services/loader/`, and `api/` has its
own `Dockerfile`. Point each service at Supabase Storage, CloudAMQP, and Supabase
Postgres through environment variables.

### Extractor on GitHub Actions

`.github/workflows/salim-extractor.yml` runs a single poll every six hours and
can also be started manually. The first run for a store is a full backfill
because `<store>_extractor_last_poll_time` does not exist yet. Later runs read
that checkpoint, process through the poll's start time, and update it only
after RabbitMQ confirms the messages.

The extractor requires the `SUPABASE_ACCESS_SECRET_KEY`, `S3_ENDPOINT_URL`, and
`RABBITMQ_URL` repository secrets and the `SUPABASE_ACCESS_KEY_ID` repository
variable. See `.env.example` for optional tuning variables.

### Loader on GitHub Actions

The `Load queue into Supabase` workflow runs every five minutes and can also
be started manually. It drains `raw-prices` in batches, exits after the queue
has been idle for 30 seconds, and has a 15-minute safety timeout. If the runner
is stopped mid-batch, RabbitMQ redelivers those messages because the loader only
acknowledges them after the database transaction commits.

Configure these repository secrets under **Settings → Secrets and variables →
Actions**:

- `RABBITMQ_URL`: the CloudAMQP AMQPS connection URL.
- `SUPABASE_DATABASE_URL`: the Supabase Postgres connection string. Prefer the
  transaction pooler URL (port 6543) for this short-lived scheduled job and add
  `+psycopg2` to the scheme, for example
  `postgresql+psycopg2://...:...@...pooler.supabase.com:6543/postgres`.

Do not commit either connection string. Scheduled workflows only run from the
repository's default branch, so merge the workflow before expecting the cron
trigger to fire.
