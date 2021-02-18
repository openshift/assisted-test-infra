import logging
from concurrent.futures import ThreadPoolExecutor


def _safe_run(job, job_id, done_handler):
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


def run_concurrently(jobs, done_handler=None, max_workers=5, timeout=2 ** 31):
    result = {}
    if isinstance(jobs, (list, tuple)):
        jobs = dict(enumerate(jobs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [(job_id, executor.submit(_safe_run, *(job, job_id, done_handler)))
                   for job_id, job in jobs.items()]
        for job_id, future in futures:
            result[job_id] = future.result(timeout=timeout)

    return result
