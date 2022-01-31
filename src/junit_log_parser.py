#!/usr/bin/env python3
import json
import re
import uuid
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional

from junit_xml import TestCase, TestSuite, to_xml_report_string

from service_client import log, SuppressAndLog


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
    error: Optional[str] = None


LOG_FORMAT = r'time="(?P<time>(.*?))" ' \
             r'level=(?P<level>(.*?)) ' \
             r'msg="(?P<msg>.*)" ' \
             r'func=(?P<func>.*) ' \
             r'file="(?P<file>(.*?))" ' \
             r'(error="(?P<error>.*)")?'

LEADER_ELECTION_LOG_FORMAT = r'(?P<level>[IEW](\d{4})) (?P<time>.*?) .*? \d (?P<file>.*?)] (?P<msg>.*)'

EXPORTED_LOG_LEVELS = ("fatal", "error")
EXPORTED_EVENT_LEVELS = ("critical", "error")


class LogsConverter:

    @classmethod
    def _is_duplicate_entry(cls, entry: LogEntry, entry_message: str, fail_cases: Dict[str, List[TestCase]]) -> bool:
        for case in fail_cases.get(entry.func, []):
            if case.failures and case.failures[0].message == entry_message:
                return True
        return False

    @classmethod
    def get_log_entry_case(cls, entry: LogEntry,
                           fail_cases: Dict[str, List[TestCase]],
                           suite_name: str,
                           failure_message: str
                           ) -> List[TestCase]:
        fail_case: List[TestCase] = list()

        if cls._is_duplicate_entry(entry, failure_message, fail_cases):
            return []

        test_case = TestCase(name=entry.func, classname=suite_name, category=suite_name, timestamp=entry.time)
        test_case.failures.append(CaseFailure(message=failure_message, output=failure_message, type=entry.level))
        fail_case.append(test_case)

        if entry.level != "fatal":
            # Add test case with the same name so it will be marked in PROW as flaky
            flaky_test_case = TestCase(name=entry.func, classname=suite_name, category=suite_name)
            fail_case.append(flaky_test_case)

        return fail_case

    @classmethod
    def get_level(cls, level: str):
        return {"e": "error", "w": "warning", "f": "fatal"}.get(level.lower()[0], "info")

    @classmethod
    def get_log_entry(cls, line: str):
        values_match = re.match(LOG_FORMAT, line) or re.match(LEADER_ELECTION_LOG_FORMAT, line)
        if values_match is None:
            return None
        values = values_match.groupdict()

        # Update values to match assisted-service logs
        values["level"] = cls.get_level(values["level"])
        if "func" not in values:
            values["func"] = values["file"].split(":")[0]

        return LogEntry(**values)

    @classmethod
    def get_failure_cases(cls, log_file_name: Path, suite_name: str) -> List[TestCase]:
        fail_cases: Dict[str, List[TestCase]] = dict()

        with open(log_file_name) as f:
            for line in f:
                entry = cls.get_log_entry(line)
                if entry is None or (entry.level not in EXPORTED_LOG_LEVELS):
                    continue

                failure_message = f"{entry.msg}\n{entry.error if entry.error else ''}"

                if entry.func not in fail_cases:
                    fail_cases[entry.func] = cls.get_log_entry_case(entry, fail_cases, suite_name, failure_message)
                else:
                    for case in fail_cases[entry.func]:
                        if case.is_failure():
                            failure = case.failures[0]
                            failure.message += f"\n{failure_message}"
                            failure.output += f"\n{failure_message}"

        log.info(f"Found {len(fail_cases)} failures on {suite_name} suite")

        return [c for cases in fail_cases.values() for c in cases]

    @classmethod
    def export_service_logs_to_junit_suites(cls, source_dir: Path, report_dir: Path):
        suites = list()
        for file in source_dir.glob("logs_assisted-service*.log"):
            suite_name = Path(file).stem.replace("logs_", "")
            log.info(f"Creating test suite from {suite_name}.log")
            test_cases = cls.get_failure_cases(file, suite_name)
            timestamp = test_cases[0].timestamp if test_cases else None
            suites.append(TestSuite(name=suite_name, test_cases=test_cases, timestamp=timestamp))

        log.info(f"Generating xml file for {len(suites)} suites")
        xml_report = to_xml_report_string(suites)
        with open(report_dir.joinpath(f"junit_log_parser_{str(uuid.uuid4())[:8]}.xml"), "w") as f:
            log.info(f"Exporting {len(suites)} suites xml-report with {len(xml_report)} characters to {f.name}")
            f.write(xml_report)


class EventsConverter:
    @classmethod
    def get_event_test_cases(cls, events_data: dict) -> List[TestCase]:
        test_cases = list()
        for event in events_data["items"]:
            test_case = cls.get_event_test_case(event)
            if test_case is not None:
                test_cases.append(test_case)

        return test_cases

    @classmethod
    def get_event_test_case(cls, event: dict) -> Optional[TestCase]:
        event_type = event["type"]
        if event_type.lower() not in EXPORTED_EVENT_LEVELS:
            return None

        log.info(f"Adding {event_type} event as test-case")
        reason = event["reason"]
        involved_object = event["involvedObject"]
        obj = involved_object["kind"].lower() + "/" + involved_object["name"]
        message = event["message"]
        timestamp = event["firstTimestamp"]
        test_case = TestCase(name=f"{reason}: {obj}", classname="EVENT", category=reason, timestamp=timestamp)
        test_case.failures.append(CaseFailure(message=message, output=message, type=event_type))
        return test_case

    @classmethod
    def export_service_events_to_junit_suite(cls, source_dir: Path, report_dir: Path, events_file_name="k8s_events.json"):
        with open(source_dir.joinpath(events_file_name)) as f:
            events_data = json.load(f)

        log.info(f"Creating test suite from service events json file - {events_file_name}")
        test_cases = cls.get_event_test_cases(events_data)

        log.info(f"Generating events xml file")
        xml_report = to_xml_report_string(test_suites=[TestSuite(name="EVENTS", test_cases=test_cases)])
        with open(report_dir.joinpath(f"junit_events_parser_{str(uuid.uuid4())[:8]}.xml"), "w") as f:
            log.info(f"Exporting events xml-report with {len(test_cases)} events to {f.name}")
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
        LogsConverter.export_service_logs_to_junit_suites(Path(args.src), report_dir)

    with SuppressAndLog(BaseException):
        log.info(f"Parsing service events from `{args.src}` to `{report_dir}`")
        EventsConverter.export_service_events_to_junit_suite(Path(args.src), report_dir)


if __name__ == '__main__':
    log.info("Initializing attempt for creating JUNIT report from service logs")
    main()
