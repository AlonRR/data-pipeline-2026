# SQLAlchemy models shared by the worker and api services.
# TODO: define a Quote model with a unique constraint on a hash of the
# quote text (see README milestone M2 — this is what makes the worker's
# upsert idempotent).

from sqlalchemy.orm import declarative_base

Base = declarative_base()
