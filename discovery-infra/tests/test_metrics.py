import time
import requests

from tests.base_test import BaseTest

SCRAPES = 3
OPEN_BRACKET = "{"
CLOSE_BRACKET = "}"
METRICS_DELIMITER = "\n"
CLUSTER_ID_LABEL = "clusterId"


def _parse_metric_labeles(metric):
    labels_str = metric[metric.find(OPEN_BRACKET) + 1:
                        metric.find(CLOSE_BRACKET)]
    return dict(item.split("=") for item in labels_str.split(","))


def _parse_metrics(raw_metrics):
    metrics = dict()
    for metric in raw_metrics:
        metric_name = metric.split(OPEN_BRACKET)[0]
        metric_labels = _parse_metric_labeles(metric)
        metric_value = metric.split(CLOSE_BRACKET)[1]

        try:
            metrics[metric_name].append((metric_labels, metric_value))

        except KeyError:
            metrics[metric_name] = [(metric_labels, metric_value)]

    return metrics


def _scrape_metrics(metrics_endpoint):
    raw_metrics = set()
    for _ in range(SCRAPES):
        response = requests.get(metrics_endpoint)
        response_data = [m for m in response.text.split(METRICS_DELIMITER) if
                         CLUSTER_ID_LABEL in m]
        raw_metrics.update(response_data)
        time.sleep(1)
    return raw_metrics


def get_metrics(metrics_endpoint):
    raw_metrics = _scrape_metrics(metrics_endpoint)
    return _parse_metrics(raw_metrics)


def get_label_metric_data_points(metrics, metric_name, label):
    return set([metric[label].replace('"', '') for metric
                in metrics[metric_name]])


def filter_metric_datapoints_by_label_value(metrics, metric_name, label_name,
                                            label_value):
    metric_datapoints = metrics.get(metric_name)
    filtered_datapoints = []
    if not metric_datapoints:
        # No such metric in scrapes metrics
        return filtered_datapoints

    for labels, value in metric_datapoints:
        if labels[label_name].replace('"', '') == label_value:
            filtered_datapoints.append({"labels": label_name, "value": value})

    return filtered_datapoints


class TestMetrics(BaseTest):
    def test_metric_create_cluster(self, api_client, cluster):
        cluster_create_metric = 'service_assisted_installer_cluster_creations'
        expected_metric_value = ' 1'
        c = cluster()
        metrics_endpoint = api_client.inventory_url + '/metrics'
        metrics = get_metrics(metrics_endpoint)
        filtered_datapoints = filter_metric_datapoints_by_label_value(
            metrics, cluster_create_metric, CLUSTER_ID_LABEL, c.id)
        # Verify that we have data points
        assert bool(filtered_datapoints)
        # Verify that the metric value looks as expected
        assert filtered_datapoints[0]["value"] == expected_metric_value
