import logging
import os
import tarfile
import time
from tempfile import TemporaryDirectory

from test_infra.consts import NUMBER_OF_MASTERS

OC_DOWNLOAD_LOGS_INTERVAL = 5 * 60
OC_DOWNLOAD_LOGS_TIMEOUT = 60 * 60


def verify_logs_uploaded(
    cluster_tar_path, expected_min_log_num, installation_success, verify_control_plane=False, check_oc=False
):
    assert os.path.exists(cluster_tar_path), f"{cluster_tar_path} doesn't exist"

    with TemporaryDirectory() as tempdir:
        with tarfile.open(cluster_tar_path) as tar:
            logging.info(f"downloaded logs: {tar.getnames()}")
            assert len(tar.getnames()) >= expected_min_log_num, (
                f"{tar.getnames()} " f"logs are less than minimum of {expected_min_log_num}"
            )
            tar.extractall(tempdir)
            for gz in os.listdir(tempdir):
                if "bootstrap" in gz:
                    _verify_node_logs_uploaded(tempdir, gz)
                    _verify_bootstrap_logs_uploaded(tempdir, gz, installation_success, verify_control_plane)
                elif "master" in gz or "worker" in gz:
                    _verify_node_logs_uploaded(tempdir, gz)
                elif "controller" in gz:
                    if check_oc:
                        _verify_oc_logs_uploaded(os.path.join(tempdir, gz))


def wait_and_verify_oc_logs_uploaded(cluster, cluster_tar_path):
    try:
        cluster.wait_for_logs_complete(
            timeout=OC_DOWNLOAD_LOGS_TIMEOUT, interval=OC_DOWNLOAD_LOGS_INTERVAL, check_host_logs_only=False
        )
        cluster.download_installation_logs(cluster_tar_path)
        assert os.path.exists(cluster_tar_path), f"{cluster_tar_path} doesn't exist"
        _verify_oc_logs_uploaded(cluster_tar_path)
    except BaseException as err:
        logging.exception("oc logs were not uploaded")
        raise


def _check_entry_from_extracted_tar(component, tarpath, verify):
    with TemporaryDirectory() as tempdir:
        logging.info(f"open tar file {tarpath}")
        with tarfile.open(tarpath) as tar:
            logging.info(f"verifying downloaded logs: {tar.getnames()}")
            tar.extractall(tempdir)
            extractedfiles = os.listdir(tempdir)
            assert any(component in logfile for logfile in extractedfiles), f"can not find {component} in logs"
            component_tars = [
                logfile for logfile in extractedfiles if (component in logfile and logfile.endswith(".gz"))
            ]
            if component_tars:
                verify(os.path.join(tempdir, component_tars[0]))


def _verify_oc_logs_uploaded(cluster_tar_path):
    _check_entry_from_extracted_tar(
        "controller",
        cluster_tar_path,
        lambda path: _check_entry_from_extracted_tar("must-gather", path, lambda inner: None),
    )


def _verify_node_logs_uploaded(dir_path, file_path):
    gz = tarfile.open(os.path.join(dir_path, file_path))
    logs = gz.getnames()
    for logs_type in ["agent.logs", "installer.logs", "mount.logs"]:
        assert any(logs_type in s for s in logs), f"{logs_type} isn't found in {logs}"
    gz.close()


def _verify_bootstrap_logs_uploaded(dir_path, file_path, installation_success, verify_control_plane=False):
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
        # if bootstrap able to ssh to other masters, test that control-plane directory is not empty
        if verify_control_plane:
            cp_full_path = os.path.join(dir_path, cp_path)
            master_dirs = os.listdir(cp_full_path)
            assert len(master_dirs) == NUMBER_OF_MASTERS - 1, (
                f"expecting {cp_full_path} to have " f"{NUMBER_OF_MASTERS - 1} values"
            )
            logging.info(f"control-plane directory has sub-directory for each master: {master_dirs}")
            for ip_dir in master_dirs:
                logging.info(f"{ip_dir} content: {os.listdir(os.path.join(cp_full_path, ip_dir))}")
                assert len(os.listdir(os.path.join(cp_full_path, ip_dir))) > 0, f"{cp_path}/{ip_dir} is empty"
        lb.close()
    gz.close()


def verify_logs_are_current(started_cluster_install_at, logs_collected_at):
    for collected_at in logs_collected_at:
        # if host timestamp is set at all- check that the timestamp is from the last installation
        if collected_at > time.time() - 86400000:
            assert collected_at > started_cluster_install_at, (
                f"logs collected at {collected_at}" f" before start time {started_cluster_install_at}"
            )
