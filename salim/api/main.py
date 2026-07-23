# FastAPI read API over the prices data.
# Expected env var: DATABASE_URL

from fastapi import FastAPI

app = FastAPI(title="Salim Price API")


@app.get("/health")
def health():
    return {"status": "ok"}


# TODO: GET /stores, GET /products/{id}, GET /prices endpoints
# (see shared/models.py for the underlying tables and api/schemas.py for response shapes)
