from kubernetes import client, config, watch


def wait_for_pod_ready(namespace: str, selector: str):
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(
        func=v1.list_namespaced_pod, namespace=namespace, label_selector=selector, timeout_seconds=300
    ):
        containers_ready = 0
        for status in event["object"].status.container_statuses:
            if status.ready:
                containers_ready += 1

        if len(event["object"].status.container_statuses) == containers_ready:
            w.stop()
            return


def get_field_from_resource(resource: dict, path: str) -> str | dict | list:
    parts = path.split(".")
    current = resource

    for part in parts:
        if "[" in part and "]" in part:
            key, index = part.split("[")
            index = int(index.rstrip("]"))

            if not isinstance(current, dict) or key not in current:
                raise KeyError(f"Key '{key}' not found in {current}")
            current = current[key]

            if not isinstance(current, list):
                raise TypeError(f"Expected a list at '{key}', but got {type(current).__name__}")
            if index >= len(current):
                raise IndexError(f"Index {index} out of range for list at '{key}'")
            current = current[index]
        else:
            if not isinstance(current, dict) or part not in current:
                raise KeyError(f"Key '{part}' not found in {current}")
            current = current[part]

    return current
