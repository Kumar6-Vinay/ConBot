import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("conbot")

# httpx logs every request URL at INFO — search URLs contain the user's
# question, which must not reach the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
