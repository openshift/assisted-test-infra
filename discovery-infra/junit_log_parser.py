#!/usr/bin/env python3
import re
import uuid
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import List

from junit_xml import TestCase, TestSuite, to_xml_report_string

from logger import log, SuppressAndLog


@dataclass
class CaseFailure:
    message: str
    output: str = ""
    type: str = ""

    def __getitem__(self, item):
        return self.__getattribute__(item)


@dataclass
class LogEntry:
    time: str = None
    level: str = None
    msg: str = None
    func: str = None
    file: str = None


LOG_FORMAT = r'time="(?P<time>(.*?))" ' \
             r'level=(?P<level>(.*?)) ' \
             r'msg="(?P<msg>.*)" ' \
             r'func=(?P<func>.*) ' \
             r'file="(?P<file>(.*?))"'

EXPORTED_LOG_LEVELS = ("fatal", "error")
EXPORTED_EVENT_LEVELS = ("critical", "error")


def get_failure_cases(log_file_name: Path, suite_name: str) -> List[TestCase]:
    fail_cases = list()

    with open(log_file_name) as f:
        for line in f:
            values = re.match(LOG_FORMAT, line)
            if values is None:
                continue

            entry = LogEntry(**values.groupdict())
            if entry.level not in EXPORTED_LOG_LEVELS:
                continue

            test_case = TestCase(name=entry.func, classname=suite_name, category=log_file_name, timestamp=entry.time)
            test_case.failures.append(CaseFailure(message=entry.msg, output=entry.msg, type=entry.level))
            fail_cases.append(test_case)

            # test is flaky
            if entry.level != "fatal":
                # Add test case with the same name so it will be marked in PROW as flaky
                flaky_test_case = TestCase(name=entry.func, classname=suite_name, category=log_file_name)
                fail_cases.append(flaky_test_case)

    log.info(f"Found {len(fail_cases)} failures on {suite_name} suite")
    return fail_cases


def export_service_logs_to_junit_suites(source_dir: Path, report_dir: Path):
    suites = list()
    for file in source_dir.glob("k8s_assisted-service*.log"):
        suite_name = Path(file).stem
        log.info(f"Creating test suite from {suite_name}.log")
        test_cases = get_failure_cases(file, suite_name)
        timestamp = test_cases[0].timestamp if test_cases else None
        suites.append(TestSuite(name=suite_name, test_cases=test_cases, timestamp=timestamp))

    log.info(f"Generating xml file for {len(suites)} suites")
    xml_report = to_xml_report_string(suites)
    with open(report_dir.joinpath(f"junit_log_parser_{str(uuid.uuid4())[:8]}.xml"), "w") as f:
        log.info(f"Exporting {len(suites)} suites xml-report with {len(xml_report)} characters to {f.name}")
        f.write(xml_report)


def main():
    parser = ArgumentParser(description="Logs junit parser")
    parser.add_argument("--src", help="Logs dir source", type=str)
    parser.add_argument("--dst", help="Junit XML report destination", type=str)
    args = parser.parse_args()

    report_dir = Path(args.dst)
    report_dir.mkdir(exist_ok=True)

    with SuppressAndLog(BaseException):
        log.info(f"Parsing logs from `{args.src}` to `{report_dir}`")
        export_service_logs_to_junit_suites(Path(args.src), report_dir)


if __name__ == '__main__':
    log.info("Initializing attempt for creating JUNIT report from service logs")
    main()
