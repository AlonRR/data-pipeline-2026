import gzip
import unittest
from unittest.mock import Mock, patch

from prices import parse_prices
from promotions import parse_promotions
from main import Checkpoint, Settings, parser_for, process_object


PRICE_XML = b"""<Root><ChainId>1</ChainId><StoreId>2</StoreId><Items><Item>
<ItemCode>123</ItemCode><ItemName>Milk</ItemName><ItemPrice>7.5</ItemPrice>
<bIsWeighted>0</bIsWeighted><PriceUpdateTime>2026-08-28 10:00:00</PriceUpdateTime>
</Item></Items></Root>"""

PROMO_XML = b"""<Root><ChainID>1</ChainID><StoreID>2</StoreID><Promotions><Promotion>
<PromotionID>p1</PromotionID><MinQty>2</MinQty><DiscountedPrice>10</DiscountedPrice>
<PromotionItems><Item><ItemCode>123</ItemCode></Item></PromotionItems>
</Promotion></Promotions></Root>"""


class ParserTests(unittest.TestCase):
    def test_gzipped_price(self):
        self.assertEqual(list(parse_prices(gzip.compress(PRICE_XML)))[0]["price"], 7.5)

    def test_flat_promotion_inherits_values(self):
        item = list(parse_promotions(PROMO_XML))[0]["items"][0]
        self.assertEqual((item["minQty"], item["discountPrice"]), (2, 10))

    def test_dispatch_ignores_checkpoint_files(self):
        self.assertIs(parser_for("store/PriceFull-a.gz"), parse_prices)
        self.assertIs(parser_for("store/PromoFull-a.gz"), parse_promotions)
        self.assertIsNone(parser_for("store_extractor_last_poll_time"))

    def test_checkpoint_handles_equal_timestamp_keys(self):
        checkpoint = Checkpoint(Mock(), "SalimPrices", "store")
        checkpoint.load = Mock(return_value={"timestamp": "2026-08-28T10:00:00+00:00", "keys": ["store/a"]})
        self.assertTrue(checkpoint.contains("store/a", "2026-08-28T10:00:00+00:00"))
        self.assertFalse(checkpoint.contains("store/b", "2026-08-28T10:00:00+00:00"))
        self.assertFalse(checkpoint.contains("store/c", "2026-08-28T11:00:00+00:00"))

    @patch("main.download", return_value=b"xml")
    @patch("main.parser_for")
    def test_publishes_records_in_transactions(self, parser_for_mock, _download_mock):
        parser_for_mock.return_value = lambda _raw: iter({"itemCode": str(i)} for i in range(5))
        channel = Mock(is_open=True)
        checkpoint = Mock()
        checkpoint.contains.return_value = False
        settings = Settings(
            rabbit_url="amqp://example",
            output_queue="raw-prices",
            bucket="SalimPrices",
            poll_interval=1,
            batch_size=30,
            publish_batch_size=2,
        )

        count = process_object(
            channel,
            settings,
            Mock(),
            "store/PriceFull-test.gz",
            "2026-08-29T10:00:00+00:00",
            checkpoint,
        )

        self.assertEqual(count, 5)
        self.assertEqual(channel.basic_publish.call_count, 5)
        self.assertEqual(channel.tx_commit.call_count, 3)
        checkpoint.save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
