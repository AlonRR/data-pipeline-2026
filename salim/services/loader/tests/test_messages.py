import unittest
from decimal import Decimal

from messages import InvalidMessage, PriceMessage, PromotionMessage, parse_message


PRICE = {
    "superProvider": "7290027600007",
    "storeId": "005",
    "itemCode": "7290000066318",
    "itemType": 1,
    "itemName": "חלב תנובה 3% 1 ליטר",
    "manufactureName": "תנובה",
    "unitQuantity": "ליטר",
    "quantity": 1,
    "unitOfMeasure": "ליטר",
    "weighted": False,
    "inPackage": 1,
    "price": 6.9,
    "updateTime": "2026-08-17T06:01:00",
}

PROMOTION = {
    "promotionId": "123",
    "providerId": "7290027600007",
    "storeId": "005",
    "description": "2 ב-20",
    "startTime": "2026-08-17T00:00:00",
    "endTime": "2026-08-24T23:59:59",
    "updateTime": "2026-08-17T06:01:00",
    "items": [
        {"itemCode": "729", "itemType": 1, "discountType": 1, "minQty": 2, "maxQty": None,
         "discountPrice": 20.0, "discountedPricePerMida": None},
    ],
}


class ParseMessageTest(unittest.TestCase):
    def test_price_record_is_recognised(self):
        msg = parse_message(PRICE)
        self.assertIsInstance(msg, PriceMessage)
        self.assertEqual(msg.provider, "7290027600007")
        self.assertEqual(msg.store_id, "005")
        self.assertEqual(msg.item_code, "7290000066318")
        self.assertEqual(msg.price, Decimal("6.9"))
        self.assertEqual(msg.item_name, "חלב תנובה 3% 1 ליטר")

    def test_promotion_record_is_recognised(self):
        msg = parse_message(PROMOTION)
        self.assertIsInstance(msg, PromotionMessage)
        self.assertEqual(msg.provider, "7290027600007")
        self.assertEqual(msg.promotion_id, "123")
        self.assertEqual(len(msg.items), 1)
        self.assertEqual(msg.items[0].item_code, "729")
        self.assertEqual(msg.items[0].min_qty, Decimal("2"))

    def test_promotion_with_malformed_item_is_invalid(self):
        for malformed in ({"discountPrice": 20}, "not an object"):
            with self.subTest(malformed=malformed):
                with self.assertRaises(InvalidMessage):
                    parse_message(dict(PROMOTION, items=[malformed]))

    def test_promotion_without_items_field_is_invalid(self):
        without_items = {key: value for key, value in PROMOTION.items() if key != "items"}
        with self.assertRaises(InvalidMessage):
            parse_message(without_items)

    def test_price_without_store_is_invalid(self):
        bad = dict(PRICE, storeId=None)
        with self.assertRaises(InvalidMessage):
            parse_message(bad)

    def test_unknown_shape_is_invalid(self):
        with self.assertRaises(InvalidMessage):
            parse_message({"hello": "world"})

    def test_non_object_is_invalid(self):
        with self.assertRaises(InvalidMessage):
            parse_message(["not", "a", "record"])


if __name__ == "__main__":
    unittest.main()
