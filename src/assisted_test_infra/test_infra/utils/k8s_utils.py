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
