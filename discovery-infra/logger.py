# -*- coding: utf-8 -*-
import logging
import re
import sys
from contextlib import suppress


class SensitiveFormatter(logging.Formatter):
    """Formatter that removes sensitive info."""

    @staticmethod
    def _filter(s):
        # Dict filter
        s = re.sub(r"('_pull_secret':\s+)'(.*?)'", r"\g<1>'*** PULL_SECRET ***'", s)
        s = re.sub(r"('_ssh_public_key':\s+)'(.*?)'", r"\g<1>'*** SSH_KEY ***'", s)

        # Object filter
        s = re.sub(r"(pull_secret='[^']*(?=')')", "pull_secret = *** PULL_SECRET ***", s)
        s = re.sub(r"(ssh_public_key='[^']*(?=')')", "ssh_public_key = *** SSH_KEY ***", s)
        return s

    def format(self, record):
        original = logging.Formatter.format(self, record)
        return self._filter(original)


class suppressAndLog(suppress):
    def __exit__(self, exctype, excinst, exctb):
        res = super().__exit__(exctype, excinst, exctb)

        if res:
            log.exception(exctype)

        return res


logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

log = logging.getLogger("")
log.setLevel(logging.DEBUG)
fmt = SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(thread)d - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(
    SensitiveFormatter(
        "%(asctime)s %(levelname)-10s - %(thread)d - %(message)s \t" "(%(pathname)s:%(lineno)d)"
    )
)
log.addHandler(ch)

fh = logging.FileHandler(filename="test_infra.log")
fh.setFormatter(fmt)
log.addHandler(fh)
