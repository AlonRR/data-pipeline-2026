"""PriceFull XML -> normalized price records. Implements issue #24.

Israeli price-transparency "Prices" files list one row per SKU-in-store:
current price, unit of measure, package quantity, etc. Structurally simpler
than the Promotions files (a sibling file type, same gov.il price-transparency
spec, handled by a separate PR) -- no groups, nothing inherited from a parent
element -- but they share the same chain quirks (tag casing drifts, e.g.
``ChainId`` vs ``ChainID``) and the crawlers upload these gzipped under the
same "prices.zip"-that's-actually-.gz naming.

Per issue #24's two options (one JSON per file vs. one JSON per item), this
takes the per-item route: ``parse_prices`` yields one flat record per
``<Item>``, ``storeId`` included on each -- so each record is already the
unit a queue message / DB upsert wants, with no unpacking on the consumer
side.

Field names in the output records (``superProvider``, ``itemDescription``,
``unitQuantity``, ``weighted``, ``inPackage``, ``lastSaleDateTime``, ...)
match the JSON schema in issue #24 exactly, not the source XML tag names --
the latter were checked by hand against real downloads from eight chains
(Shufersal, Wolt, Hazi Hinam, Rami Levi, Tiv Taam, SuperPharm, Victory, and
two different Yohananof schema eras) and drift between chains more than
you'd guess: ``ManufactureName``/``ManufactureItemDescription`` (no "r"),
``PriceUpdateTime`` (not ...Date), and Wolt spells ``bIsWeighted`` as
``blsWeighted``. ``LastSaleDateTime`` is present for most chains but
entirely absent from Wolt's -- ``_text()`` returns ``None`` for a missing
tag, so that's handled, not a bug.

Not wired into any trigger yet -- no queue consumer, no scheduler. This is
just a library (plus a small CLI for ad-hoc use) to be called once the
pipeline decides when/what to run it on; see ``main.py``.
"""
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


def decompress(raw: bytes) -> bytes:
    """Gunzip *raw* if it is gzipped, otherwise return it untouched.

    The crawlers upload single gzipped XML files (despite "prices.zip"
    naming), but a few sources serve the XML uncompressed under the same name.
    """
    return gzip.decompress(raw) if raw[:2] == _GZIP_MAGIC else raw


def _text(element: ET.Element | None, *tags: str) -> str | None:
    """First non-blank direct child matching any of *tags*, case-insensitively."""
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
    if raw is None:
        return None
    return raw.strip() in ("1", "true", "True")


# Wolt's real files spell this tag "blsWeighted" (lowercase L, lowercase s)
# instead of the "bIsWeighted" every other observed chain uses -- a genuine
# source-side typo, not a casing difference our case-insensitive _text()
# would catch, so it needs to be listed as a distinct alias.
_WEIGHTED_TAGS = ("bIsWeighted", "blsWeighted")


def _timestamp(raw: str | None) -> str | None:
    """ISO 8601 timestamp from a "YYYY-MM-DD HH:MM:SS"-style value."""
    return raw.replace(" ", "T") if raw else None


def _items_of(root: ET.Element) -> list[ET.Element]:
    """The <Item> elements under the file's <Items> container, wherever it is."""
    container = next(
        (c for c in root if isinstance(c.tag, str) and c.tag.lower() == "items"),
        None,
    )
    return list(container) if container is not None else []


def _item_record(item: ET.Element, super_provider: str | None, store_id: str | None) -> dict:
    return {
        "superProvider": super_provider,
        "storeId": store_id,
        "itemCode": _text(item, "ItemCode"),
        "itemType": _number(_text(item, "ItemType")),
        "itemName": _text(item, "ItemName", "ItemNm"),
        "itemDescription": _text(item, "ManufactureItemDescription", "ManufacturerItemDescription", "ItemDescription"),
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
        # Wolt's files omit this tag altogether -- _text() already returns
        # None for a missing tag, so that's fine, not a bug.
        "lastSaleDateTime": _timestamp(_text(item, "LastSaleDateTime", "LastSaleDate")),
    }


def parse_prices(raw: bytes) -> Iterator[dict]:
    """Yield one normalized record per ``<Item>`` in a PriceFull file."""
    root = ET.fromstring(decompress(raw))
    super_provider = _text(root, "ChainId", "ChainID")
    store_id = _text(root, "StoreId", "StoreID")

    for item in _items_of(root):
        yield _item_record(item, super_provider, store_id)


# --------------------------------------------------------------------------- #
# S3 access -- mirrors crawler.py's Uploader client setup (same fail-fast
# timeouts), just for reading instead of writing.
# --------------------------------------------------------------------------- #
def build_s3_client(
    endpoint_url: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    region: str | None = None,
):
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
    """Fetch one object's raw bytes from S3 (still gzipped, if uploaded that way)."""
    client = client or build_s3_client()
    obj = client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    log.info("downloaded s3://%s/%s (%d bytes)", bucket, key, len(body))
    return body


def extract_prices(bucket: str, key: str, client=None) -> list[dict]:
    """Download + decompress + parse a PriceFull object in one call."""
    return list(parse_prices(download(bucket, key, client=client)))


def to_json(records) -> str:
    return json.dumps(list(records), ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Ad-hoc CLI: python Prices.py <bucket> <key> -- prints the JSON records.
# Not a service entrypoint (that's main.py); useful for manual runs/testing
# until the pipeline decides how this gets triggered.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) != 3:
        print("usage: python Prices.py <bucket> <key>")
        raise SystemExit(1)

    _bucket, _key = sys.argv[1], sys.argv[2]
    _client = build_s3_client(
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        access_key=os.environ.get("S3_ACCESS_KEY"),
        secret_key=os.environ.get("S3_SECRET_KEY"),
        region=os.environ.get("S3_REGION"),
    )
    print(to_json(extract_prices(_bucket, _key, client=_client)))
