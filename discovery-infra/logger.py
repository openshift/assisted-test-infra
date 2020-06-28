# -*- coding: utf-8 -*-
import logging
import sys

logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

log = logging.getLogger("")
log.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)-10s %(message)s \t" "(%(pathname)s:%(lineno)d)"
    )
)
log.addHandler(ch)

fh = logging.FileHandler(filename="test_infra.log")
fh.setFormatter(format)
log.addHandler(fh)
