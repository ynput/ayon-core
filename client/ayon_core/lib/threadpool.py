import logging
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Optional

log = logging.getLogger(__name__)


def as_completed_stop_and_raise_on_error(
        executor: ThreadPoolExecutor,
        futures: List[Future],
        logger: Optional[logging.Logger] = None):
    """For the ThreadPoolExecutor shutdown and cancel futures as soon one of
    the workers raises an error as they complete.

    The ThreadPoolExecutor only cancels pending futures on exception but will
    still complete those that are running - each which also themselves could
    fail. We log all exceptions, but re-raise the last exception only.
    """
    if logger is None:
        logger = log

    for future in concurrent.futures.as_completed(futures):
        exception = future.exception()
        if exception:
            # As soon as an error occurs, stop executing more futures.
            # Running workers however, will still complete so we also want
            # to log those errors if any occurred on them.
            executor.shutdown(wait=True, cancel_futures=True)
            break
    else:
        # Futures are completed, no exceptions occurred
        return

    # An exception occurred in at least one future. Get exceptions from
    # all futures that are done and ended up failing until that point.
    exceptions = []
    for future in futures:
        if not future.cancelled() and future.done():
            exception = future.exception()
            if exception:
                exceptions.append(exception)

    # Log any exceptions that occurred in all workers
    for exception in exceptions:
        logger.error("Error occurred in worker", exc_info=exception)

    # Raise the last exception
    raise exceptions[-1]
