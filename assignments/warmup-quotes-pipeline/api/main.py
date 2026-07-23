# FastAPI read endpoints over the quotes table (shared/models.py):
#   GET /quotes       - paginated list, filterable by author and tag
#   GET /quotes/{id}
#   GET /stats         - avg word count, top 3 authors by quote count
#
# Expected env vars: DATABASE_URL, API_HOST, API_PORT

from fastapi import FastAPI

app = FastAPI(title="Warmup Quotes API")
