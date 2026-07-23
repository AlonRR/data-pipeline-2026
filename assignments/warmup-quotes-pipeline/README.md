# Warm-up: Quotes Pipeline

A small solo warm-up before we build [`salim`](../../salim/README.md) together.
Same shape — crawl → queue → worker → db → api — at a scale you can finish
alone in about **4 hours**, entirely with `docker compose` (no cloud accounts
needed).

## What you're building

```
crawler --> RabbitMQ ("quotes" queue) --> worker --> Postgres --> FastAPI
 (scrape)        (one message/quote)     (enrich +      (quotes       (read
                                           upsert)        table)       endpoints)
```

1. **crawler** scrapes [quotes.toscrape.com](https://quotes.toscrape.com/) (a
   static site built for scraping practice) and publishes one message per
   quote to a RabbitMQ queue.
2. **worker** consumes the queue, enriches each quote (word count, longest
   word, a simple sentiment score), and upserts it into Postgres.
3. **api** exposes read endpoints over the stored quotes.

## Folder structure

```
warmup-quotes-pipeline/
  docker-compose.yml   # infra (Postgres, RabbitMQ) + your 3 services
  .env.example          # copy to .env
  shared/                # DB engine + model, used by worker and api
  crawler/               # scrape quotes.toscrape.com, publish to queue
  worker/                # consume queue, enrich, upsert into Postgres
  api/                    # FastAPI read endpoints
```

## Running it

```bash
cd assignments/warmup-quotes-pipeline
cp .env.example .env
docker compose up --build
```

- RabbitMQ management UI: http://localhost:15672 (guest/guest)
- API docs: http://localhost:8000/docs

Everything you need to fill in is marked `TODO` in the stub files.

## Milestones

Work through these **in order** and commit after each one (conventional
commits, per [CONTRIBUTING.md](../../CONTRIBUTING.md)). Don't skip ahead —
each stage only makes sense once the previous one actually runs.

### M1 — Crawler (`crawler/crawler.py`)

Scrape `CRAWLER_SOURCE_URL` (see `.env.example`), following pagination
(`/page/2/`, etc.) up to `CRAWLER_MAX_PAGES`. For each quote, publish a
JSON message to the `RABBITMQ_QUEUE` queue with at least:

```json
{"text": "...", "author": "...", "tags": ["...", "..."], "source_url": "..."}
```

`git commit -m "feat(crawler): scrape quotes.toscrape.com and publish to queue"`

### M2 — Worker (`worker/main.py`, `shared/models.py`)

Consume messages and, for each one:

- Compute `word_count` and `longest_word`.
- Compute a `sentiment_score`: a simple lexicon-based count (positive words
  minus negative words — write or find a small word list, no ML needed).
- Upsert into a `quotes` table.

**Idempotency requirement:** the worker must be safely restartable. If the
same message is processed twice (e.g. RabbitMQ redelivers after a crash),
the second run must **not** create a duplicate row. Give the table a unique
constraint on a hash of the quote text and upsert on conflict — don't just
`INSERT`.

`git commit -m "feat(worker): consume queue, enrich quotes, idempotent upsert"`

### M3 — API (`api/main.py`, `api/schemas.py`)

- `GET /quotes` — paginated list, filterable by `author` and `tag`.
- `GET /quotes/{id}`
- `GET /stats` — average word count, top 3 authors by quote count.

`git commit -m "feat(api): add read endpoints over quotes table"`

### M4 — Prove the idempotency works

Republish the same handful of messages to the queue (or stop the worker
mid-batch and restart it) and confirm row count in `/stats` doesn't change.
Write this as a short test or a documented manual repro — either is fine,
but it has to be checkable by someone else.

`git commit -m "test(worker): verify duplicate messages don't create duplicate rows"`

### M5 — Design note

Add a short "Design notes" section to this README (below) explaining:

- Why you chose your dedupe key / hash approach.
- What happens if the worker crashes after upserting but before acking the
  message (and why that's the safe direction to fail in).

`git commit -m "docs(readme): add design notes"`

## Using AI tools

Use them freely — but you should be able to explain, without looking it up,
**why** the idempotency approach in M2 works and what breaks if you remove
it. That's the one part of this warm-up that's actually about pipelines
rather than syntax; everything else is scaffolding to get you there.

## Deliverables checklist

- [ ] `docker compose up --build` runs all 5 services with no manual steps
- [ ] Crawler publishes real scraped quotes, not fixture data
- [ ] Worker upsert is idempotent (M4 proof included)
- [ ] API endpoints from M3 all work (check `/docs`)
- [ ] Design notes section filled in below
- [ ] `git status` is clean of `.venv/`, `.env`, logs, etc.

## Stretch goals (optional)

- Add a `GET /quotes/search?q=` full-text search endpoint.
- Handle a quote whose text changes on re-scrape (should it update the row
  or be treated as a new quote?) — document your choice.
- Rate-limit the crawler so it's polite to the source site.

---

## Design notes

_(fill in during M5)_
