
"""Three-hour S3 delta poller and RabbitMQ publisher.

Source objects are never deleted. A durable high-water mark per store is kept
in S3, so container restarts and deployments do not cause a full replay.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import timezone

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

    @classmethod
    def from_env(cls):
        return cls(
            rabbit_url=os.environ["RABBITMQ_URL"],
            output_queue=os.environ.get("RABBITMQ_QUEUE", "raw-prices"),
            bucket=os.environ.get("S3_BUCKET", "SalimPrices"),
            poll_interval=max(1, int(os.environ.get("EXTRACTOR_POLL_INTERVAL_SECONDS", "10800"))),
        )


class Checkpoint:
    """Per-store S3 high-water mark plus keys at that exact timestamp."""

    def __init__(self, client, bucket: str, store: str):
        self.client, self.bucket = client, bucket
        self.key = f"{store}_extractor_last_poll_time"

    def load(self) -> dict:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self.key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return {"timestamp": "", "keys": []}
            raise
        return json.loads(obj["Body"].read())

    def contains(self, key: str, timestamp: str) -> bool:
        state = self.load()
        return timestamp < state["timestamp"] or (timestamp == state["timestamp"] and key in state["keys"])

    def save(self, key: str, timestamp: str) -> None:
        state = self.load()
        if timestamp > state["timestamp"]:
            state = {"timestamp": timestamp, "keys": [key]}
        elif timestamp == state["timestamp"] and key not in state["keys"]:
            state["keys"].append(key)
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


def process_object(channel, settings: Settings, client, key: str, timestamp: str) -> int:
    bucket = settings.bucket
    parser = parser_for(key)
    if parser is None:
        log.info("ignoring unsupported object %s", key)
        return 0
    store = key.split("/", 1)[0] if "/" in key else "salim"
    checkpoint = Checkpoint(client, bucket, store)
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


def list_supported_objects(client, bucket: str):
    """Yield every supported object using S3 pagination.

    S3's API is flat even when keys contain store prefixes, which avoids one
    list request per directory and works for both MinIO and Supabase Storage.
    """
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            key = item["Key"]
            if parser_for(key) is not None:
                yield key, item["LastModified"].astimezone(timezone.utc).isoformat()


def poll_once(channel, settings: Settings, client) -> dict[str, int]:
    """Process the S3 delta in stable timestamp/key order."""
    pending = []
    checkpoints = {}
    for key, timestamp in list_supported_objects(client, settings.bucket):
        store = key.split("/", 1)[0] if "/" in key else "salim"
        checkpoint = checkpoints.setdefault(store, Checkpoint(client, settings.bucket, store))
        if not checkpoint.contains(key, timestamp):
            pending.append((timestamp, key))

    results = {}
    for timestamp, key in sorted(pending):
        count = process_object(channel, settings, client, key, timestamp)
        store = key.split("/", 1)[0] if "/" in key else "salim"
        results[store] = results.get(store, 0) + count
    log.info("poll complete: %d object(s), %d record(s)", len(pending), sum(results.values()))
    return results


def run() -> None:
    settings = Settings.from_env()
    client = s3_client()
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(settings.rabbit_url))
            channel = connection.channel()
            channel.queue_declare(queue=settings.output_queue, durable=True)
            channel.confirm_delivery()
            poll_once(channel, settings, client)
            connection.close()
            log.info("next poll in %d seconds", settings.poll_interval)
            time.sleep(settings.poll_interval)
        except KeyboardInterrupt:
            return
        except Exception:
            log.exception("worker connection failed; retrying")
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()
