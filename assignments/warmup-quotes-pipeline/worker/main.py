# Consumes quote messages from RABBITMQ_QUEUE, enriches each one
# (word_count, longest_word, sentiment_score — see README milestone M2),
# and upserts it into the quotes table (shared/models.py).
#
# Must be idempotent: redelivering the same message must not create a
# duplicate row. Only ack a message after the upsert commits.
#
# Expected env vars: RABBITMQ_URL, RABBITMQ_QUEUE, DATABASE_URL


if __name__ == "__main__":
    print("Starting the worker...")
