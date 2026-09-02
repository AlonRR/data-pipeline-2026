# Triggering extractors from S3

**Status:** Accepted  
**Decision:** Poll the `SalimPrices` S3 bucket every three hours and process a
per-store delta.

## Design

The extractor uses S3 `ListObjectsV2` pagination and considers only
`PriceFull*` and `PromoFull*` objects. Objects are grouped logically by the
first component of their key (`<store>/<filename>`).

Each store has a durable checkpoint object at:

```text
s3://SalimPrices/<store>_extractor_last_poll_time
```

The checkpoint body is JSON:

```json
{
  "timestamp": "2026-08-28T10:00:00+00:00",
  "keys": ["shufersal/PriceFull-example.gz"]
}
```

`keys` disambiguates objects with the same S3 `LastModified` timestamp. On
each poll, an object is selected when its timestamp is above the watermark, or
when it has the same timestamp and its key is not recorded.

Objects are processed in `(LastModified, key)` order. For every object, the
worker downloads and parses it, publishes persistent JSON messages using
RabbitMQ publisher confirms, and only then advances the checkpoint. S3 source
objects are never deleted.

RabbitMQ messages use deterministic IDs derived from bucket, object key, and
record index. Consumers should use those IDs for idempotent writes because a
process crash after broker confirmation but before checkpoint persistence can
cause safe at-least-once redelivery.

## Backfill

Deleting or moving a store's checkpoint aside causes the next poll to replay
all supported objects for that store. To backfill from a chosen point, replace
the checkpoint with the desired ISO-8601 timestamp and an empty `keys` array.

## Operations

- Default interval: `EXTRACTOR_POLL_INTERVAL_SECONDS=10800`.
- S3 listing is paginated; bucket size does not truncate discovery.
- Run one scheduler instance. If extraction later needs horizontal scaling,
  introduce a dedicated job queue or distributed lease before adding replicas.
- A failed download, parse, publish, or checkpoint write fails the poll and is
  retried after the worker reconnect delay; its checkpoint is not advanced.
