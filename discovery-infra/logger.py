import logging
import atexit

logger = logging.getLogger("Assisted-Test-Infra")  # pylint: disable=invalid-name
FORMATTER = logging.Formatter('%(asctime)s %(levelname)-10s [%(name)s] %(message)s')
CONSOLE_HANDLER = logging.StreamHandler()
CONSOLE_HANDLER.setFormatter(FORMATTER)
logger.addHandler(CONSOLE_HANDLER)
FILE_HANDLER = logging.FileHandler(filename="test_infra.log")
atexit.register(FILE_HANDLER.close)
FILE_HANDLER.setFormatter(logging.Formatter('%(asctime)s %(levelname)-10s %(message)s \t'
                                            '(%(pathname)s:%(lineno)d)'))
logger.addHandler(FILE_HANDLER)
