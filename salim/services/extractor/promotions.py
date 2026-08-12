"""PromoFull XML -> normalized promotion records.

Israeli price-transparency PromoFull files come in two shapes. Shufersal and
Hazi Hinam wrap items in groups::

    Promotion/Groups/Group/PromotionItems/PromotionItem

while the Cerberus-hosted chains (Yohananof, Victory) hang the items straight
off the promotion and put MinQty/DiscountedPrice at promotion level instead::

    Promotion/PromotionItems/Item

Both normalize to the same record here: anything the source states at
promotion or group level is pushed *down* onto every item, so a consumer only
ever reads per-item fields from one place and never has to know which variant
a file came from.

Naming drifts too, and not just in casing — ``PromotionStartDateTime`` vs a
``PromotionStartDate``/``PromotionStartHour`` pair, ``PromotionUpdateTime`` vs
``PromotionUpdateDate``, ``<PromotionItem>`` vs ``<Item>``. Lookups are
case-insensitive and accept the known aliases. Empty elements
(``<MaxQty></MaxQty>``, very common) become ``None`` rather than ``0`` or
``""`` — absent is not the same as zero for a quantity or price.
"""
from __future__ import annotations

import gzip
import logging
import xml.etree.ElementTree as ET
from typing import Iterator

log = logging.getLogger("salim.extractor.promotions")

_GZIP_MAGIC = b"\x1f\x8b"

# Fields the source may state at promotion or group level; each is inherited by
# an item that doesn't state its own. Keys are the output names.
_INHERITED = {
    "discountType": "DiscountType",
    "minQty": "MinQty",
    "maxQty": "MaxQty",
    "discountPrice": "DiscountedPrice",
    "discountedPricePerMida": "DiscountedPricePerMida",
}


def _text(element: ET.Element | None, *tags: str) -> str | None:
    """First non-blank direct child matching any of *tags*, case-insensitively.

    Tags are tried in the order the children appear, not the order given, so
    aliases that never co-occur in one file can be passed together freely.
    """
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


def _timestamp(element: ET.Element, date_tags: tuple[str, ...], hour_tag: str | None = None) -> str | None:
    """ISO 8601 timestamp from a date(-time) element plus an optional hour.

    Chains split this inconsistently: some put a full datetime in the date tag
    (``PromotionStartDateTime``) and repeat the time in the hour tag, others
    give a bare date (``PromotionStartDate``) and keep the time only in the
    hour tag.
    """
    date = _text(element, *date_tags)
    if not date:
        return None
    date = date.replace(" ", "T")
    if "T" in date:
        return date
    hour = (_text(element, hour_tag) if hour_tag else None) or "00:00:00"
    return f"{date}T{hour}"


def _inherited_values(element: ET.Element, fallback: dict) -> dict:
    values = dict(fallback)
    for name, tag in _INHERITED.items():
        raw = _text(element, tag)
        if raw is not None:
            values[name] = _number(raw)
    return values


def _item_record(item: ET.Element, inherited: dict) -> dict:
    record = {"itemCode": _text(item, "ItemCode"), "itemType": _number(_text(item, "ItemType"))}
    for name, tag in _INHERITED.items():
        raw = _text(item, tag)
        record[name] = _number(raw) if raw is not None else inherited.get(name)
    return record


def _items_of(group: ET.Element) -> list[ET.Element]:
    """The item elements under a group's ``<PromotionItems>``.

    The child tag is ``<PromotionItem>`` in the grouped variant but ``<Item>``
    in the Cerberus one, so take whatever elements are in there rather than
    matching on name.
    """
    container = next(
        (c for c in group if isinstance(c.tag, str) and c.tag.lower() == "promotionitems"),
        None,
    )
    return list(container) if container is not None else []


def _promotion_record(promotion: ET.Element, chain_id: str | None, store_id: str | None) -> dict:
    promotion_level = _inherited_values(promotion, {})

    # No <Groups> means the flat variant: the promotion itself is the one group.
    groups = promotion.findall("Groups/Group") or [promotion]
    items = [
        _item_record(item, _inherited_values(group, promotion_level))
        for group in groups
        for item in _items_of(group)
    ]

    return {
        "promotionId": _text(promotion, "PromotionID"),
        "providerId": chain_id,
        "storeId": store_id,
        "description": _text(promotion, "PromotionDescription"),
        "startTime": _timestamp(
            promotion, ("PromotionStartDateTime", "PromotionStartDate"), "PromotionStartHour"
        ),
        "endTime": _timestamp(
            promotion, ("PromotionEndDateTime", "PromotionEndDate"), "PromotionEndHour"
        ),
        "updateTime": _timestamp(promotion, ("PromotionUpdateTime", "PromotionUpdateDate")),
        "items": items,
    }


def decompress(raw: bytes) -> bytes:
    """Gunzip *raw* if it is gzipped, otherwise return it untouched.

    The crawlers upload single gzipped XML files (despite the README saying
    "zip"), but a few sources serve the XML uncompressed under the same name.
    """
    return gzip.decompress(raw) if raw[:2] == _GZIP_MAGIC else raw


def parse_promotions(raw: bytes) -> Iterator[dict]:
    """Yield one normalized record per ``<Promotion>`` in a PromoFull file."""
    root = ET.fromstring(decompress(raw))
    chain_id = _text(root, "ChainID")
    store_id = _text(root, "StoreID")

    for promotion in root.iter():
        if isinstance(promotion.tag, str) and promotion.tag.lower() == "promotion":
            yield _promotion_record(promotion, chain_id, store_id)
