# Scrapes CRAWLER_SOURCE_URL (quotes.toscrape.com), following pagination up
# to CRAWLER_MAX_PAGES, and publishes one JSON message per quote to the
# RABBITMQ_QUEUE queue: {"text", "author", "tags", "source_url"}.
#
# Expected env vars: CRAWLER_SOURCE_URL, CRAWLER_MAX_PAGES, RABBITMQ_URL,
# RABBITMQ_QUEUE


if __name__ == "__main__":
    print("Starting the crawler...")
