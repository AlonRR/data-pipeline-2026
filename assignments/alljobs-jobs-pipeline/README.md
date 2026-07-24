# Assignment: AllJobs Hi-Tech Jobs Pipeline

Build a small data pipeline over the [AllJobs Hi-Tech jobs portal](https://www.alljobs.co.il/Partners/Hitech/)
listings, using **two different collection techniques against the same
site** — this is the point of the assignment, not a detail of it:

1. **Internal read API** — AllJobs' own frontend loads listing data from a
   JSON endpoint it calls internally. It isn't documented publicly; you
   find it yourself using your browser's devtools Network tab. This is a
   real skill: most sites you'll scrape professionally don't ship a public
   API, but plenty expose an internal one their own frontend uses.
2. **HTML parsing** — the internal API typically returns only summary
   fields (title, company, location, tags). The full job description,
   requirements, and other detail-page-only fields aren't in that
   response, so you fetch each job's page and parse the rendered HTML
   directly.

You'll wire both into the same pipeline shape we've used all course:
crawl → queue → worker → db → api.

## ⚠️ Read-only, and validate before you build

- Your crawler must only ever issue **read (GET) requests**. Never call an
  endpoint that would create, update, or delete anything on AllJobs —
  there's no reason your listing/detail fetches should need to.
- **`alljobs.co.il/robots.txt` was already checked**: it disallows a set
  of admin/upload paths and a few landing/search-feed patterns, but does
  **not** block an `/api/` path or any job listing/search page — unlike
  the two other sites we ruled out first (Drushim disallows its jobs API
  when queried with `area=`/`jobcode=`; JobMaster disallows `/api/`
  entirely). That's why AllJobs is the pick. Still re-check the live file
  yourself before you start (`robots.txt` files change) and rate-limit
  your requests regardless (a fixed delay between calls — don't
  parallelize your crawler against the live site).
- Sites like this often run bot protection (Cloudflare/PerimeterX-style
  challenges) that can block plain `requests` calls even when nothing
  above is violated. **Don't assume this works** — a proof-of-concept
  pass against the real, live site is the first step (see `poc/` at the
  repo root, gitignored, for scratch work), before committing to this as
  the assignment for the whole class.

## Architecture

```
crawler --> RabbitMQ ("jobs" queue) --> worker --> Postgres --> FastAPI
 (two          (one message/job,        (normalize +   (jobs        (read
  sources)      merged A+B)              idempotent      table)      endpoints)
                                          upsert)
```

## The two sources, in detail

### Source A — internal read API

1. Open the [AllJobs Hi-Tech jobs portal](https://www.alljobs.co.il/Partners/Hitech/)
   (or the underlying search page,
   `SearchResultsGuest.aspx?position=235&...` for the Software category)
   in a browser with devtools open, Network tab filtered to XHR/fetch.
2. Browse a few pages / apply a filter and watch for the JSON request(s)
   that return listing data.
3. Document what you find (method, URL, query params, and a trimmed
   sample response) — this write-up is itself a deliverable (see
   Milestone 1).
4. Call that endpoint from your crawler to get a page of job summaries:
   at minimum `id`, `title`, `company`, `location`, `tags`/`category`,
   `posted_at`, and the listing URL.

### Source B — HTML parsing of the detail page

For each job id/URL from Source A, fetch the individual listing page and
parse (BeautifulSoup or similar) whatever fields aren't in the API
response — full description text, requirements, and salary/employment
type if shown. Merge this into the Source A record for that job before
publishing to the queue.

## Milestones

Commit after each one (conventional commits, per
[CONTRIBUTING.md](../../CONTRIBUTING.md)).

### M1 — Discover and document the internal API

Deliverable: a short `docs/api-notes.md` in this assignment folder with
the endpoint, method, params, and a sample (trimmed) JSON response you
captured from devtools.

`git commit -m "docs(alljobs-jobs-pipeline): document discovered internal jobs API"`

### M2 — Crawler, Source A

Fetch N pages of job summaries from the internal API and publish one
message per job to the `jobs` queue.

`git commit -m "feat(crawler): fetch job listings from alljobs internal api"`

### M3 — Crawler, Source B

For each job from M2, fetch and parse the detail page; merge the parsed
fields into the message before publishing.

`git commit -m "feat(crawler): parse job detail pages for fields missing from the api"`

### M4 — Worker

Consume the queue, normalize/validate each message, and upsert into a
`jobs` table. **Idempotency requirement** (same as the warm-up): the
worker must be safely restartable — redelivery of the same message must
not create a duplicate row. Unique-constrain on the job id (or a hash if
AllJobs' ids aren't stable) and upsert on conflict.

`git commit -m "feat(worker): normalize and idempotently upsert jobs"`

### M5 — API

- `GET /jobs` — paginated, filterable by `company`, `location`, `tag`.
- `GET /jobs/{id}`
- `GET /stats` — count by location/tag, or similar.

`git commit -m "feat(api): add read endpoints over jobs table"`

### M6 — Prove idempotency + design notes

Same as the warm-up: republish the same messages (or restart the worker
mid-batch) and show row count doesn't change. Add a short design-notes
section below covering your dedupe key choice and how you rate-limited
the crawler.

`git commit -m "docs(readme): add design notes"`

## Deliverables checklist

- [ ] `docs/api-notes.md` documenting the discovered internal API
- [ ] `docker compose up --build` runs the full pipeline with no manual steps
- [ ] Source A and Source B are both real (no fixture/mock data)
- [ ] Worker upsert is idempotent (M6 proof included)
- [ ] API endpoints from M5 all work (check `/docs`)
- [ ] Crawler respects `robots.txt` and rate-limits its requests
- [ ] Design notes filled in below
- [ ] `git status` clean of `.venv/`, `.env`, logs, etc.

## Stretch goals (optional)

- Detect and skip jobs that have been removed/expired on re-crawl.
- Add a `GET /jobs/search?q=` full-text search over title + description.
- Compare the internal API's rate of change to how often you need to
  re-crawl detail pages, and document the tradeoff.

---

## Design notes

_(fill in during M6)_
