import inspect
import os
import time
import traceback

import decorator
from dataclasses import dataclass
from typing import Union, Callable, Any

from junit_xml import TestCase

from .junit_test_suite import JunitTestSuite


@dataclass
class CaseFailure:
    message: str
    output: str = ""
    type: str = ""

    def __getitem__(self, item):
        return self.__getattribute__(item)


class JunitTestCase:
    """
    JunitTestCase is a decorator that represents single TestCase.
    When the decorated function finished its execution, it's registered to the relevant JunitTestSuite.
    TestCase will fail (TestCase failure) only when exception occurs during execution.
    """
    _func: Union[Callable, None]
    _case: Union[TestCase, None]

    IS_PYTEST = "PYTEST_CURRENT_TEST" in os.environ

    def __init__(self) -> None:
        self._case = None
        self._func = None

    @property
    def name(self):
        if self._func:
            return self._func.__name__

    def __call__(self, function: Callable) -> Callable:
        """
        Create a TestCase object for each executed decorated test case function and register it into the relevant
        JunitTestSuite object.
        If exception accrues during function execution, the exception is recorded as junit case failure (CaseFailure)
        and raises it.
        Execution time is being recorded and saved into the TestCase instance.
        :param function: Decorated function
        :return: Wrapped function
        """
        self._func = function

        def wrapper(_, obj: Any, *args, **kwargs):
            """
            :param _:  @ignored - Decorated test case function -
            :param obj: Class instance of which the decorated function contained in it
            :param args: Arguments passed to the function
            :param kwargs: Arguments passed to the function
            :return: function results
            """
            self._case = TestCase(name=self.name, classname=obj.__class__.__name__)
            start = time.time()

            try:
                value = function(obj, *args, **kwargs)
            except BaseException as e:
                failure = CaseFailure(message=str(e), output=traceback.format_exc(), type=e.__class__.__name__)
                self._case.failures.append(failure)
                raise
            finally:
                self._case.elapsed_sec = time.time() - start
                JunitTestSuite.register(self._case, self.get_suite_name())
            return value

        return decorator.decorator(wrapper, function)

    @classmethod
    def is_instance(cls, instance):
        return isinstance(cls, instance)

    @classmethod
    def get_suite_name(cls) -> str:
        suite_name = ""
        stack_locals = [frame_info.frame.f_locals for frame_info in inspect.stack()]
        for f_locals in [stack_local for stack_local in stack_locals
                         if "function" in stack_local and "self" in stack_local]:
            suite = f_locals["self"]
            if isinstance(suite, JunitTestSuite):
                suite_name = f_locals["function"].__name__
                break

        return suite_name
