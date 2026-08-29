
"""Three-hour S3 delta poller and RabbitMQ publisher.

Source objects are never deleted. A durable high-water mark per store is kept
in S3, so container restarts and deployments do not cause a full replay.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pika
from botocore.exceptions import ClientError

from prices import build_s3_client, download, parse_prices
from promotions import parse_promotions

log = logging.getLogger("salim.extractor")


@dataclass(frozen=True)
class Settings:
    rabbit_url: str
    output_queue: str
    bucket: str
    poll_interval: int
    batch_size: int

    @classmethod
    def from_env(cls):
        return cls(
            rabbit_url=os.environ["RABBITMQ_URL"],
            output_queue=os.environ.get("RABBITMQ_QUEUE", "raw-prices"),
            bucket=os.environ.get("S3_BUCKET", "SalimPrices"),
            poll_interval=max(1, int(os.environ.get("EXTRACTOR_POLL_INTERVAL_SECONDS", "10800"))),
            batch_size=max(1, int(os.environ.get("EXTRACTOR_BATCH_SIZE", "30"))),
        )


class Checkpoint:
    """Per-store S3 high-water mark plus keys at that exact timestamp."""

    def __init__(self, client, bucket: str, store: str):
        self.client, self.bucket = client, bucket
        self.key = f"{store}_extractor_last_poll_time"
        self._state = None

    def load(self) -> dict:
        if self._state is not None:
            return self._state
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self.key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                self._state = {"timestamp": "", "keys": []}
                return self._state
            raise
        self._state = json.loads(obj["Body"].read())
        return self._state

    def contains(self, key: str, timestamp: str) -> bool:
        state = self.load()
        return timestamp < state["timestamp"] or (timestamp == state["timestamp"] and key in state["keys"])

    def save(self, key: str, timestamp: str) -> None:
        state = self.load()
        if timestamp > state["timestamp"]:
            state = {"timestamp": timestamp, "keys": [key]}
        elif timestamp == state["timestamp"] and key not in state["keys"]:
            state["keys"].append(key)
        self._state = state
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.key,
            Body=json.dumps(state, separators=(",", ":")).encode(),
            ContentType="application/json",
        )


def parser_for(key: str):
    name = key.rsplit("/", 1)[-1].lower()
    if name.startswith("pricefull"):
        return parse_prices
    if name.startswith("promofull"):
        return parse_promotions
    return None


def s3_client():
    return build_s3_client(
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        access_key=os.environ.get("S3_ACCESS_KEY"),
        secret_key=os.environ.get("S3_SECRET_KEY"),
        region=os.environ.get("S3_REGION"),
    )


def process_object(
    channel,
    settings: Settings,
    client,
    key: str,
    timestamp: str,
    checkpoint: Checkpoint | None = None,
) -> int:
    bucket = settings.bucket
    parser = parser_for(key)
    if parser is None:
        log.info("ignoring unsupported object %s", key)
        return 0
    store = key.split("/", 1)[0] if "/" in key else "salim"
    checkpoint = checkpoint or Checkpoint(client, bucket, store)
    if checkpoint.contains(key, timestamp):
        log.info("already processed %s", key)
        return 0

    count = 0
    for index, record in enumerate(parser(download(bucket, key, client=client))):
        channel.basic_publish(
            exchange="",
            routing_key=settings.output_queue,
            body=json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode(),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
                message_id=f"{bucket}:{key}:{index}",
                headers={"source_bucket": bucket, "source_key": key},
            ),
            mandatory=True,
        )
        count += 1
    # confirm_delivery makes basic_publish wait for broker confirmation.
    checkpoint.save(key, timestamp)
    log.info("published %d record(s) from %s", count, key)
    return count


def list_supported_batches(client, bucket: str, batch_size: int):
    """Yield supported objects one S3 page at a time.

    A page is processed before the next page is requested, so a full backfill
    starts publishing immediately and memory use stays bounded.
    """
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(
        Bucket=bucket,
        PaginationConfig={"PageSize": batch_size},
    ):
        batch = []
        for item in page.get("Contents", []):
            key = item["Key"]
            if parser_for(key) is not None:
                batch.append(
                    (key, item["LastModified"].astimezone(timezone.utc).isoformat())
                )
        if batch:
            yield batch


def poll_once(channel, settings: Settings, client) -> dict[str, int]:
    """Process the S3 delta through the start time of this poll.

    A store with no checkpoint gets a full backfill. Objects uploaded after
    ``poll_cutoff`` are intentionally left for the next scheduled run.
    """
    poll_cutoff = datetime.now(timezone.utc).isoformat()
    checkpoints = {}
    results = {}
    processed_objects = 0
    scanned_objects = 0
    for batch_number, batch in enumerate(
        list_supported_batches(client, settings.bucket, settings.batch_size),
        start=1,
    ):
        scanned_objects += len(batch)
        pending = []
        for key, timestamp in batch:
            store = key.split("/", 1)[0] if "/" in key else "salim"
            checkpoint = checkpoints.setdefault(
                store,
                Checkpoint(client, settings.bucket, store),
            )
            if timestamp <= poll_cutoff and not checkpoint.contains(key, timestamp):
                pending.append((timestamp, key, checkpoint))

        log.info(
            "S3 batch %d: scanned %d supported object(s), %d pending",
            batch_number,
            len(batch),
            len(pending),
        )
        for timestamp, key, checkpoint in sorted(pending, key=lambda row: (row[0], row[1])):
            try:
                count = process_object(
                    channel,
                    settings,
                    client,
                    key,
                    timestamp,
                    checkpoint,
                )
            finally:
                # Downloads are in-memory only; force collection of the XML
                # tree and decompressed bytes before starting the next file.
                gc.collect()
            store = key.split("/", 1)[0] if "/" in key else "salim"
            results[store] = results.get(store, 0) + count
            processed_objects += 1
    log.info(
        "poll complete: scanned %d supported object(s), processed %d object(s), published %d record(s)",
        scanned_objects,
        processed_objects,
        sum(results.values()),
    )
    return results


def run_once() -> dict[str, int]:
    """Connect to RabbitMQ, execute one delta poll, and exit."""
    settings = Settings.from_env()
    client = s3_client()
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbit_url))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=settings.output_queue, durable=True)
        channel.confirm_delivery()
        return poll_once(channel, settings, client)
    finally:
        if connection.is_open:
            connection.close()


def run_forever() -> None:
    """Run the poller continuously for Docker/background-worker deployments."""
    settings = Settings.from_env()
    while True:
        try:
            run_once()
            log.info("next poll in %d seconds", settings.poll_interval)
            time.sleep(settings.poll_interval)
        except KeyboardInterrupt:
            return
        except Exception:
            log.exception("worker connection failed; retrying")
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--once" in sys.argv[1:]:
        run_once()
    else:
        run_forever()
