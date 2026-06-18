
import logging

logger = logging.getLogger("bank_app")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s", "extra": %(extra)s}'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
