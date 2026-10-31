import json
import logging

log = logging.getLogger("tarantino")


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.3f}"
    s = str(v)
    return json.dumps(s) if (" " in s or not s) else s


def emit(event: str, **fields) -> None:
    log.info(" ".join([event, *(f"{k}={_fmt(v)}" for k, v in fields.items())]))


def setup() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
