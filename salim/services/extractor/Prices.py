"""Parse PriceFull XML files into normalized price records."""
from __future__ import annotations

import gzip
import json
import logging
import xml.etree.ElementTree as ET
from typing import Iterator

import boto3
from botocore.config import Config as BotoConfig

log = logging.getLogger("salim.extractor.prices")

_GZIP_MAGIC = b"\x1f\x8b"
_WEIGHTED_TAGS = ("bIsWeighted", "blsWeighted")


def decompress(raw: bytes) -> bytes:
    """Gunzip raw bytes when needed."""
    return gzip.decompress(raw) if raw[:2] == _GZIP_MAGIC else raw


def _text(element: ET.Element | None, *tags: str) -> str | None:
    if element is None:
        return None
    wanted = {tag.lower() for tag in tags}
    for child in element:
        if isinstance(child.tag, str) and child.tag.lower() in wanted:
            value = (child.text or "").strip()
            if value:
                return value
    return None


def _number(raw: str | None) -> float | int | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        log.debug("non-numeric value %r", raw)
        return None
    return int(value) if value.is_integer() else value


def _bool(raw: str | None) -> bool | None:
    return None if raw is None else raw.strip().lower() in ("1", "true")


def _timestamp(raw: str | None) -> str | None:
    return raw.replace(" ", "T") if raw else None


def _items_of(root: ET.Element) -> list[ET.Element]:
    container = next(
        (child for child in root if isinstance(child.tag, str) and child.tag.lower() == "items"),
        None,
    )
    return list(container) if container is not None else []


def _item_record(
    item: ET.Element,
    super_provider: str | None,
    store_id: str | None,
) -> dict:
    return {
        "superProvider": super_provider,
        "storeId": store_id,
        "itemCode": _text(item, "ItemCode"),
        "itemType": _number(_text(item, "ItemType")),
        "itemName": _text(item, "ItemName", "ItemNm"),
        "itemDescription": _text(
            item,
            "ManufactureItemDescription",
            "ManufacturerItemDescription",
            "ItemDescription",
        ),
        "manufactureName": _text(item, "ManufactureName", "ManufacturerName"),
        "manufactureCountry": _text(item, "ManufactureCountry"),
        "unitQuantity": _text(item, "UnitQty"),
        "quantity": _number(_text(item, "Quantity")),
        "unitOfMeasure": _text(item, "UnitOfMeasure"),
        "weighted": _bool(_text(item, *_WEIGHTED_TAGS)),
        "inPackage": _number(_text(item, "QtyInPackage")),
        "price": _number(_text(item, "ItemPrice")),
        "allowDiscount": _bool(_text(item, "AllowDiscount")),
        "itemStatus": _text(item, "ItemStatus"),
        "updateTime": _timestamp(_text(item, "PriceUpdateTime", "PriceUpdateDate")),
        "lastSaleDateTime": _timestamp(
            _text(item, "LastSaleDateTime", "LastSaleDate")
        ),
    }


def parse_prices(raw: bytes) -> Iterator[dict]:
    """Yield one normalized record per Item in a PriceFull file."""
    root = ET.fromstring(decompress(raw))
    super_provider = _text(root, "ChainId", "ChainID")
    store_id = _text(root, "StoreId", "StoreID")
    for item in _items_of(root):
        yield _item_record(item, super_provider, store_id)


def build_s3_client(
    endpoint_url: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    region: str | None = None,
):
    """Build the S3-compatible client used by the extractor."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=BotoConfig(
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def download(bucket: str, key: str, client=None) -> bytes:
    """Download one object without modifying or deleting it."""
    client = client or build_s3_client()
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    log.info("downloaded s3://%s/%s (%d bytes)", bucket, key, len(body))
    return body


def extract_prices(bucket: str, key: str, client=None) -> list[dict]:
    """Download and parse a PriceFull object."""
    return list(parse_prices(download(bucket, key, client=client)))


def to_json(records, *, indent: int | None = None) -> str:
    """Serialize normalized records as UTF-8-friendly JSON."""
    return json.dumps(list(records), ensure_ascii=False, indent=indent)
