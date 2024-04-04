# -*- coding: utf-8 -*-
import logging
import os
import re
import sys
import traceback
from contextlib import suppress
from enum import Enum
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


class Color(Enum):
    BLUE = "\033[0;34m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    WHITE = "\033[1;37m"
    RESET = "\033[0m"


ColorLevel = {
    logging.DEBUG: Color.BLUE.value,
    logging.INFO: Color.RESET.value,
    logging.WARNING: Color.LIGHT_YELLOW.value,
    logging.ERROR: Color.LIGHT_RED.value,
    logging.CRITICAL: Color.LIGHT_PURPLE.value,
}


class ColorizingFileHandler(logging.FileHandler):
    def emit(self, record):
        if self.stream is None:
            if self.mode != "w" or not self._closed:
                self.stream = self._open()
        if self.stream:
            ColorizingStreamHandler.emit(self, record)

    @property
    def is_tty(self):
        return True


class ColorizingStreamHandler(logging.StreamHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def is_tty(self):
        isatty = getattr(self.stream, "isatty", None)
        return isatty and isatty()

    def emit(self, record):
        try:
            message = self.format(record)
            stream = self.stream
            if not self.is_tty:
                stream.write(message)
            else:
                message = ColorLevel[record.levelno] + message + Color.RESET.value
                stream.write(message)
            stream.write(getattr(self, "terminator", "\n"))
            self.flush()
        except Exception:
            self.handleError(record)


def add_log_record(test_id):
    # Adding log record for testcase id
    _former_log_record_factory = logging.getLogRecordFactory()

    def log_record_uuid_injector(*args, **kwargs):
        record = _former_log_record_factory(*args, **kwargs)
        record.test_id = test_id
        return record

    logging.setLogRecordFactory(log_record_uuid_injector)


# set test_id record to "" empty by default
add_log_record("")


def get_logging_level():
    level = os.environ.get("LOGGING_LEVEL", "")
    return logging.getLevelName(level.upper()) if level else logging.DEBUG


logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)


def add_log_file_handler(logger: logging.Logger, filename: str) -> logging.FileHandler:
    fmt = SensitiveFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(test_id)s:%(thread)d:%(process)d - %(message)s"
    )
    fh = ColorizingFileHandler(filename)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return fh


def add_stream_handler(logger: logging.Logger):
    fmt = SensitiveFormatter(
        "%(asctime)s  %(name)s %(levelname)-10s - %(thread)d - %(message)s \t" "(%(pathname)s:%(lineno)d)->%(funcName)s"
    )
    ch = ColorizingStreamHandler(sys.stderr)
    ch.setFormatter(fmt)
    logger.addHandler(ch)


logger_name = os.environ.get("LOGGER_NAME", "")
urllib3_logger = logging.getLogger("urllib3")
urllib3_logger.handlers = [logging.NullHandler()]

logging.getLogger("requests").setLevel(logging.ERROR)
urllib3_logger.setLevel(logging.ERROR)

log = logging.getLogger(logger_name)
log.setLevel(get_logging_level())

add_log_file_handler(log, "test_infra.log")
add_log_file_handler(urllib3_logger, "test_infra.log")
add_stream_handler(log)
add_stream_handler(urllib3_logger)


class SuppressAndLog(suppress):
    def __exit__(self, exctype: Type[Exception], excinst: Exception, exctb: TracebackType):
        res = super().__exit__(exctype, excinst, exctb)

        if res:
            with suppress(BaseException):
                tb_data = traceback.extract_tb(exctb, 1)[0]
                log.warning(f"Suppressed {exctype.__name__} from {tb_data.name}:{tb_data.lineno} : {excinst}")

        return res
