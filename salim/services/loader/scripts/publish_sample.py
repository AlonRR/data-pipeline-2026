"""Publish extractor-shaped JSON records to the raw-prices queue for local testing.

By default publishes a small built-in mix of price items and one promotion
(enough to exercise every loader path, including a poison message). Pass one
or more JSON files - a list of records as ``Prices.py``/``promotions.py``
emit them - to publish real data instead:

    python scripts/publish_sample.py
    python scripts/publish_sample.py --poison out/prices.json out/promos.json

Uses RABBITMQ_URL / RABBITMQ_QUEUE from the environment (defaults match
docker-compose with the RabbitMQ port published to localhost).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pika

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE = os.environ.get("RABBITMQ_QUEUE", "raw-prices")

_STORE = {"superProvider": "7290027600007", "storeId": "005"}
_COMMON = {"itemType": 1, "weighted": False, "inPackage": 1, "updateTime": "2026-08-17T06:01:00"}

SAMPLE_PRICES = [
    dict(_STORE, **_COMMON, itemCode="7290000066318", itemName="חלב תנובה 3% 1 ליטר", manufactureName="תנובה",
         unitQuantity="ליטר", quantity=1, unitOfMeasure="ליטר", price=6.9),
    dict(_STORE, **_COMMON, itemCode="7290004127336", itemName="במבה נוגט 60 גרם", manufactureName=None,
         unitQuantity="גרם", quantity=60, unitOfMeasure="100 גרם", price=4.5),
    dict(_STORE, **_COMMON, itemCode="7290000000001", itemName="מלפפון חמוץ במים 540 גרם", manufactureName="לא ידוע",
         unitQuantity="גרם", quantity=540, unitOfMeasure="100 גרם", price=8.9),
    dict(_STORE, **_COMMON, itemCode="5449000131836", itemName="קוקה קולה זירו 1.5 ליטר", manufactureName=None,
         unitQuantity="ליטר", quantity=1.5, unitOfMeasure="ליטר", price=7.9),
    dict(_STORE, **_COMMON, itemCode="7290011017408", itemName="קפה נמס נסקפה טייסטרס צ'ויס 200 גרם", manufactureName=None,
         unitQuantity="גרם", quantity=200, unitOfMeasure="100 גרם", price=32.9),
    dict(_STORE, **_COMMON, itemCode="7290106589346", itemName="גבינה צהובה עמק 28% פרוסות 200 גרם", manufactureName=None,
         unitQuantity="גרם", quantity=200, unitOfMeasure="100 גרם", price=14.9),
    dict(_STORE, **_COMMON, itemCode="100", itemName="עגבניה", manufactureName=None,
         unitQuantity="ק\"ג", quantity=1, unitOfMeasure="ק\"ג", price=5.9) | {"itemType": 0, "weighted": True},
    dict(_STORE, **_COMMON, itemCode="7290002332404", itemName="שוקולד פרה חלב עלית 100 גרם", manufactureName=None,
         unitQuantity="גרם", quantity=100, unitOfMeasure="100 גרם", price=5.5),
]

SAMPLE_PROMOTIONS = [
    {
        "promotionId": "9001", "providerId": "7290027600007", "storeId": "005",
        "description": "2 יחידות ב-10 ₪", "startTime": "2026-08-17T00:00:00", "endTime": "2026-08-24T23:59:59",
        "updateTime": "2026-08-17T06:01:00",
        "items": [
            {"itemCode": "7290004127336", "itemType": 1, "discountType": 1, "minQty": 2, "maxQty": None,
             "discountPrice": 10.0, "discountedPricePerMida": None},
            {"itemCode": "7290002332404", "itemType": 1, "discountType": 1, "minQty": 2, "maxQty": None,
             "discountPrice": 10.0, "discountedPricePerMida": None},
        ],
    }
]

POISON = [{"hello": "not a price"}, "this is not even json"]


def _records(paths: list[str], poison: bool) -> list:
    if not paths:
        records: list = [*SAMPLE_PRICES, *SAMPLE_PROMOTIONS]
    else:
        records = []
        for path in paths:
            loaded = json.loads(Path(path).read_text(encoding="utf-8"))
            records.extend(loaded if isinstance(loaded, list) else [loaded])
    return [*records, *POISON] if poison else records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="JSON files (list of records); built-in samples if omitted")
    parser.add_argument("--poison", action="store_true", help="also publish two unloadable messages")
    args = parser.parse_args(argv)

    records = _records(args.files, args.poison)
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE, durable=True)
        for record in records:
            body = record.encode() if isinstance(record, str) else json.dumps(record, ensure_ascii=False).encode()
            channel.basic_publish(
                exchange="", routing_key=QUEUE, body=body,
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
            )
    finally:
        connection.close()
    print(f"published {len(records)} messages to {QUEUE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
