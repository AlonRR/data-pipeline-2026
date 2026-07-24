# Assignment: AllJobs Hi-Tech Jobs Pipeline

Build a small data pipeline over the [AllJobs Hi-Tech jobs portal](https://www.alljobs.co.il/Partners/Hitech/)
listings, using **two different collection techniques against the same
site** — this is the point of the assignment, not a detail of it:

2. **HTML parsing** — the internal API typically returns only summary
   fields (title, company, location, tags). The full job description,
   requirements, and other detail-page-only fields aren't in that
   response, so you fetch each job's page and parse the rendered HTML
   directly.


### Source B — HTML parsing of the detail page

For each job id/URL from Source A, fetch the individual listing page and
parse (BeautifulSoup or similar) whatever fields aren't in the API
response — full description text, requirements, and salary/employment
type if shown. Merge this into the Source A record for that job before
publishing to the queue.


## TO DO
1. change the time to be timestamp
2. itarate on first 5 pages


## Deadline
31.7 before class
