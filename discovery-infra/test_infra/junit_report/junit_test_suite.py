import os
from pathlib import Path
from typing import Callable, Union, Type, Dict, List, ClassVar, Any

import decorator
from junit_xml import TestSuite, to_xml_report_string


class SuiteNotExistError(KeyError):
    """ Test Suite decorator name is not exists in suites poll """


class JunitTestSuite:
    """
    JunitTestSuite is a decorator that waits for JunitTestCases decorators to register their testcases instances.
    After all test cases has finished their execution, the JunitTestSuite instance collect all registered TestCases
    and generate junit xml accordingly.
    JunitTestSuite represents single TestSuite.
    Generated report format: junit_<Class Name>_<Suite Function Name>_report.xml
    The usage of this function is regardless of pytest unittest packages.
    """
    _junit_suites: ClassVar[Dict[str, List]] = dict()
    _report_dir: Path
    _func: Union[Callable, None]
    _suite: Union[TestSuite, None]
    _name = str

    def __init__(self, report_dir: Path = Path.cwd()):
        """
        :param report_dir: Target directory, created if not exists
        """
        self._report_dir = report_dir
        self._func = None
        self._suite = None
        self._name = None

    def __call__(self, function: Callable):
        """
        Execute test suite decorated function and export the results to junit xml file
        :param function: Decorated test suite function
        :return: Converted caller function into a decorator
        """
        self._func = function
        self._name = function.__name__
        JunitTestSuite._junit_suites[self._name] = list()

        def wrapper(_, obj: Any, *args, **kwargs):
            """
            :param _:  @ignored - Decorated test suite function -
            :param obj: Test class containing the test suite
            :param args: Function given arguments
            :param kwargs: Function given keyword arguments
            :return: Function return value
            """
            try:
                value = function(obj, *args, **kwargs)
            except BaseException:
                raise
            finally:
                self._collect(obj.__class__)
            return value

        return decorator.decorator(wrapper, function)

    def _collect(self, klass: Type[object]):
        """
        Collect all TestCases that
        :param klass: Class of which the decorated function contained in it
        :return: None
        """
        self._suite = TestSuite(name=f"{klass.__name__}_{self._name}",
                                test_cases=JunitTestSuite._junit_suites[self._name])
        self._export()

    def _export(self) -> None:
        path = self._report_dir.joinpath(f"junit_{self._suite.name}_report.xml")
        xml_string = to_xml_report_string([self._suite])

        os.makedirs(self._report_dir, exist_ok=True)
        with open(path, "w") as f:
            f.write(xml_string)

    @classmethod
    def register(cls, test_case, suite_name: str) -> None:
        """
        Register test case to the relevant test suite
        :param test_case: TestCase instance
        :param suite_name: Suite to register to
        :return: None
        """
        if suite_name not in cls._junit_suites:
            raise SuiteNotExistError(f"Can't find suite named {suite_name} for {test_case} test case")
        cls._junit_suites[suite_name].append(test_case)
