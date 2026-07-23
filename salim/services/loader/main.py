# Consumes records from the RabbitMQ queue, normalizes/validates each one,
# and upserts it into the DB (stores/products/prices tables, see shared/models.py).
#
# Expected env vars: RABBITMQ_URL, RABBITMQ_QUEUE, DATABASE_URL


if __name__ == "__main__":
    print("Starting the loader service...")
