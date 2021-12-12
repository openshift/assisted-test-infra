from typing import List

import waiting

from assisted_test_infra.test_infra.utils import utils
from service_client import InventoryClient, log


class EventsHandler:
    def __init__(self, api_client: InventoryClient):
        self.api_client = api_client

    def _find_event(
        self,
        event_to_find: str,
        reference_time: int,
        params_list: List[str] = None,
        host_id: str = "",
        infra_env_id: str = "",
        cluster_id: str = "",
    ):
        events_list = self.get_events(host_id=host_id, cluster_id=cluster_id, infra_env_id=infra_env_id)
        for event in events_list:
            if event_to_find not in event["message"]:
                continue
            # Adding a 2 sec buffer to account for a small time diff between the machine and the time on staging
            if utils.to_utc(event["event_time"]) >= reference_time - 2:
                if all(param in event["message"] for param in params_list):
                    log.info(f"Event to find: {event_to_find} exists with its params")
                    return True
        return False

    def get_events(self, host_id: str = "", cluster_id: str = "", infra_env_id: str = ""):
        return self.api_client.get_events(cluster_id=cluster_id, host_id=host_id, infra_env_id=infra_env_id)

    def wait_for_event(
        self,
        event_to_find: str,
        reference_time: int,
        params_list: List[str] = None,
        host_id: str = "",
        infra_env_id: str = "",
        cluster_id: str = "",
        timeout: int = 10,
    ):
        log.info(f"Searching for event: {event_to_find}")
        if params_list is None:
            params_list = list()
        waiting.wait(
            lambda: self._find_event(event_to_find, reference_time, params_list, host_id, infra_env_id, cluster_id),
            timeout_seconds=timeout,
            sleep_seconds=2,
            waiting_for=f"event {event_to_find}",
        )
