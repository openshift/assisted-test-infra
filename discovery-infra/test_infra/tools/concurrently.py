import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Tuple, Union, Any


def _safe_run(job, job_id: int, done_handler: Callable[[int], None]):
    call = None
    try:
        call, call_args = job[0], job[1:]
        return call(*call_args)
    except BaseException:
        logging.debug("When concurrently running '%(call)s'", dict(call=str(call)))
        raise
    finally:
        if done_handler:
            done_handler(job_id)


def run_concurrently(
    jobs: Union[List, Dict, Tuple],
    done_handler: Callable[[int], None] = None,
    max_workers: int = 5,
    timeout: float = 2 ** 31,
) -> Dict[int, Any]:
    result = {}
    if isinstance(jobs, (list, tuple)):
        jobs = dict(enumerate(jobs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [(job_id, executor.submit(_safe_run, *(job, job_id, done_handler))) for job_id, job in jobs.items()]
        for job_id, future in futures:
            result[job_id] = future.result(timeout=timeout)

    return result
