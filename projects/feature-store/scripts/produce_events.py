"""Send synthetic user events to Kafka so the stack can be exercised locally.

python scripts/produce_events.py --n 500 --bootstrap localhost:9092
"""

import argparse
import json
import random
import time
import uuid

from kafka import KafkaProducer


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--users", type=int, default=20)
    p.add_argument("--bootstrap", default="localhost:9092")
    p.add_argument("--topic", default="user_events")
    a = p.parse_args()

    producer = KafkaProducer(bootstrap_servers=a.bootstrap, value_serializer=lambda v: json.dumps(v).encode())
    now = int(time.time())
    for _ in range(a.n):
        user = f"user-{random.randint(1, a.users)}"
        producer.send(
            a.topic,
            key=user.encode(),
            value={
                "event_id": str(uuid.uuid4()),
                "user_id": user,
                "event_type": random.choice(["view", "add_to_cart", "checkout"]),
                "timestamp": now - random.randint(0, 7200),
                "session_duration": random.randint(5, 900),
                "items_viewed": random.randint(0, 12),
                "cart_value": round(random.choice([0, 0, 19.99, 49.5, 120.0, 899.0]), 2),
                "device_type": random.choice(["mobile", "desktop"]),
            },
        )
    producer.flush()
    print(f"sent {a.n} events to {a.topic}")


if __name__ == "__main__":
    main()
