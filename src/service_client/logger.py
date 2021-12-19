# -*- coding: utf-8 -*-
import logging
import re
import sys
import traceback
import uuid
from contextlib import suppress
from types import TracebackType
from typing import Type


class SensitiveFormatter(logging.Formatter):
    """Formatter that removes sensitive info."""

    @staticmethod
    def _filter(s):
        # Dict filter
        s = re.sub(r"('_pull_secret':\s+)'(.*?)'", r"\g<1>'*** PULL_SECRET ***'", s)
        s = re.sub(r"('_ssh_public_key':\s+)'(.*?)'", r"\g<1>'*** SSH_KEY ***'", s)
        s = re.sub(r"('_vsphere_username':\s+)'(.*?)'", r"\g<1>'*** VSPHERE_USER ***'", s)
        s = re.sub(r"('_vsphere_password':\s+)'(.*?)'", r"\g<1>'*** VSPHERE_PASSWORD ***'", s)

        # Object filter
        s = re.sub(r"(pull_secret='[^']*(?=')')", "pull_secret = *** PULL_SECRET ***", s)
        s = re.sub(r"(ssh_public_key='[^']*(?=')')", "ssh_public_key = *** SSH_KEY ***", s)
        s = re.sub(r"(vsphere_username='[^']*(?=')')", "vsphere_username = *** VSPHERE_USER ***", s)
        s = re.sub(r"(vsphere_password='[^']*(?=')')", "vsphere_password = *** VSPHERE_PASSWORD ***", s)

        return s

    def format(self, record):
        original = logging.Formatter.format(self, record)
        return self._filter(original)


logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

log = logging.getLogger("")
log.setLevel(logging.DEBUG)
fmt = SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(thread)d - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(
    SensitiveFormatter("%(asctime)s %(levelname)-10s - %(thread)d - %(message)s \t" "(%(pathname)s:%(lineno)d)")
)
log.addHandler(ch)


def add_log_file_handler(filename: str) -> logging.FileHandler:
    fh = logging.FileHandler(filename)
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return fh


log_filename = f"test_infra_{str(uuid.uuid4())[:8]}.log"
add_log_file_handler(log_filename)


class SuppressAndLog(suppress):
    def __exit__(self, exctype: Type[Exception], excinst: Exception, exctb: TracebackType):
        res = super().__exit__(exctype, excinst, exctb)

        if res:
            with suppress(BaseException):
                tb_data = traceback.extract_tb(exctb, 1)[0]
                log.warning(f"Suppressed {exctype.__name__} from {tb_data.name}:{tb_data.lineno} : {excinst}")

        return res
