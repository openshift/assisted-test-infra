import logging
import os
import shutil
import tarfile
import time
from tempfile import TemporaryDirectory

from test_infra.consts import NUMBER_OF_MASTERS


def verify_logs_uploaded(cluster_tar_path, expected_min_log_num, installation_success):
    assert os.path.exists(cluster_tar_path), f"{cluster_tar_path} doesn't exist"

    with TemporaryDirectory() as tempdir:
        with tarfile.open(cluster_tar_path) as tar:
            logging.info(f'downloaded logs: {tar.getnames()}')
            assert len(tar.getnames()) >= expected_min_log_num, f"{tar.getnames()} logs are less than minimum of {expected_min_log_num}"
            tar.extractall(tempdir)
            for gz in os.listdir(tempdir):
                if "bootstrap" in gz:
                    _verify_node_logs_uploaded(tempdir, gz)
                    _verify_bootstrap_logs_uploaded(tempdir, gz, installation_success)
                elif "master" in gz or "worker" in gz:
                    _verify_node_logs_uploaded(tempdir, gz)


def _verify_node_logs_uploaded(dir_path, file_path):
    gz = tarfile.open(os.path.join(dir_path, file_path))
    logs = gz.getnames()
    for logs_type in ["agent.logs", "installer.logs", "mount.logs"]:
        assert any(logs_type in s for s in logs), f"{logs_type} isn't found in {logs}"
    gz.close()


def _verify_bootstrap_logs_uploaded(dir_path, file_path, installation_success):
    gz = tarfile.open(os.path.join(dir_path, file_path))
    logs = gz.getnames()
    assert any("bootkube.logs" in s for s in logs), f"bootkube.logs isn't found in {logs}"
    if not installation_success:
        for logs_type in ["dmesg.logs", "log-bundle"]:
            assert any(logs_type in s for s in logs), f"{logs_type} isn't found in {logs}"
        # test that installer-gather gathered logs from all masters
        lb_path = [s for s in logs if "log-bundle" in s][0]
        gz.extract(lb_path, dir_path)
        lb = tarfile.open(os.path.join(dir_path, lb_path))
        lb.extractall(dir_path)
        cp_path = [s for s in lb.getnames() if "control-plane" in s][0]
        assert len(os.listdir(os.path.join(dir_path, cp_path))) == NUMBER_OF_MASTERS - 1, f"expecting {os.listdir(os.path.join(dir_path, cp_path))} to have {NUMBER_OF_MASTERS - 1} values"
        lb.close()
    gz.close()


def verify_logs_are_current(started_cluster_install_at, logs_collected_at):
    for collected_at in logs_collected_at:
        # if host timestamp is set at all- check that the timestamp is from the last installation
        if collected_at > time.time() - 86400000:
            assert collected_at > started_cluster_install_at, f"logs collected at {collected_at} before start time {started_cluster_install_at}"
