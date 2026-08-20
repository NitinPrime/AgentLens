import asyncio
import logging
import os

import redis.asyncio as redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agentlens-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def main() -> None:
    """Hold a Redis connection open and heartbeat.

    Ingestion, analytics, and evaluations all run inline in the API request path,
    so there is no queue to drain yet. This process exists so the deployment
    topology is already in place for the first job that needs to move off the
    request path — long evaluation sweeps being the obvious candidate.
    """

    logger.info("AgentLens worker starting...")
    client = redis.from_url(REDIS_URL, decode_responses=True)

    try:
        pong = await client.ping()
        logger.info("Connected to Redis: %s", pong)
        logger.info("Worker ready. No job queue is in use yet; holding a heartbeat.")
        while True:
            await asyncio.sleep(30)
            logger.debug("Worker heartbeat")
    except asyncio.CancelledError:
        logger.info("Worker shutting down")
    finally:
        await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
