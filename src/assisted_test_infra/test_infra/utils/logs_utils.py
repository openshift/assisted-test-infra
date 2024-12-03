import contextlib
import copy
import hashlib
import os
import random
import shutil
import tarfile
import time
from pathlib import Path
from string import ascii_lowercase
from tempfile import TemporaryDirectory

from assisted_service_client.rest import ApiException

from consts import NUMBER_OF_MASTERS

from service_client import log

import waiting

OC_DOWNLOAD_LOGS_INTERVAL = 5 * 60
OC_DOWNLOAD_LOGS_TIMEOUT = 60 * 60
MAX_LOG_SIZE_BYTES = 1_000_000
# based on '-- No entries --' size in file
MIN_LOG_SIZE_BYTES = 17


@contextlib.contextmanager
def _safe_open_tar(tar_path: Path | str, destination_path: Path | str) -> None:
    """Return a safe-to-be-extracted tarfile object.

    Handling CVE-2007-4559, which is relevant to extraction of tar files
    that expand outside of destination directory. Basically it might attempt
    extracting to sensitive paths such as /etc/passwd (assuming process is
    having the proper permissions to do so) which means additional sanitization
    is needed to be made before calling `extractall / extract`.
    """
    destination_path = Path(destination_path)
    with tarfile.open(tar_path) as tar:
        for member in tar.getmembers():
            if not (destination_path / member.name).resolve().is_relative_to(destination_path.resolve()):
                raise RuntimeError(f"Attempted writing into {member.name}, which is outside {destination_path}!")

        yield tar


def _verify_duplicate_and_size_logs_file(dir_path: str) -> None:
    """Verify logs files with different content and minimal size
    Assuming all files under directory are file type
    Checking:
    Repeated names under directory
    Repeated md5sum under directory
    Included file name inside other files
    Exceed limit size (1MB) under directory
    Minimal file size (17 Bytes) when '-- No entries --'
    :param dir_path:
    :return: None
    """
    files = os.listdir(dir_path)
    # assert if repeated md5sum means same files content or empty
    md5_list = [_get_file_md5sum(dir_path, file) for file in files]
    log.info(f"Checking repeated md5sum for files {str(files)}")
    assert len(md5_list) == len(set(md5_list)), f"Repeated md5sum content file or empty logs {str(files)}"
    # assert if one of the file larger than 1 MB
    log.info(f"Checking file size exceed {MAX_LOG_SIZE_BYTES} bytes")
    size_list = list(
        map(lambda the_file, the_dir=dir_path: os.stat(os.path.join(the_dir, the_file)).st_size, os.listdir(dir_path))
    )
    assert not any(
        size_file > MAX_LOG_SIZE_BYTES for size_file in size_list
    ), f"exceed size limit {MAX_LOG_SIZE_BYTES} from {str(files)}"
    # check if file name exists in current list names, ex "m1" in [m1.copy, m1.1]
    for f in files:
        copy_files = copy.deepcopy(files)
        copy_files.remove(f)
        for copy_file in copy_files:
            assert not (f in copy_file), f"{f} in {copy_files}"


def _get_file_md5sum(dir_path: str, file_path: str) -> str:
    with open(os.path.join(dir_path, file_path), "rb") as file_to_check:
        data = file_to_check.read()
        md5_returned = hashlib.md5(data).hexdigest()
        log.info(f"calculate md5sum for {os.path.join(dir_path, file_path)} is {md5_returned}")
    return md5_returned


def verify_logs_uploaded(
    cluster_tar_path,
    expected_min_log_num,
    installation_success,
    verify_control_plane=False,
    check_oc=False,
    verify_bootstrap_errors=False,
):
    """Uploaded log verification
    Tree from service installation logs:
    -- cluster_zzzzzzz.tar
        -- cluster_events.json
        -- cluster_metadata.json
        -- manifest_system-generated_openshift*.yaml
        -- controller_logs.tar.gz
            -- controller_logs
                -- assisted-installer-controller.logs
        -- test-cluster-master_worker-x.tar
            -- test-cluster-master-worker-x.tar.gz
                -- test-cluster-master-worker-x
                    -- log_host_zzzz:
                        -- agents.logs
                        -- installer.logs
                        -- mount.logs
                        -- report.logs
        -- test-cluster-bootstrap-master-z.tar
            -- test-cluster-bootstrap-master-z.tar.gz
                -- test-cluster-bootstrap-master-z
                    -- log_host_yyyyy:
                        -- agents.logs
                        -- installer.logs
                        -- mount.logs
                        -- report.logs
                        -- bootkube.logs

    :param cluster_tar_path:
    :param expected_min_log_num:
    :param installation_success:
    :param verify_control_plane:
    :param check_oc:
    :param verify_bootstrap_errors:
    :return: None
    """
    assert os.path.exists(cluster_tar_path), f"{cluster_tar_path} doesn't exist"

    with TemporaryDirectory() as tempdir:
        with _safe_open_tar(cluster_tar_path, tempdir) as tar:
            log.info(f"downloaded logs: {tar.getnames()}")
            assert len(tar.getnames()) >= expected_min_log_num, (
                f"{tar.getnames()} " f"logs are less than minimum of {expected_min_log_num}"
            )
            assert len(tar.getnames()) == len(set(tar.getnames())), f"Repeated tar file names {str(tar.getnames())}"
            tar.extractall(tempdir)
            """Verify one level with duplication and size for extracted files, example for success installation:
            ['test-infra-cluster-6c2d0ab7_master_test-infra-cluster-6c2d0ab7-master-2.tar',
             'test-infra-cluster-6c2d0ab7_master_test-infra-cluster-6c2d0ab7-master-0.tar',
             'test-infra-cluster-6c2d0ab7_bootstrap_test-infra-cluster-6c2d0ab7-master-1.tar',
             'cluster_events.json', 'cluster_metadata.json', 'controller_logs.tar.gz']
            """
            _verify_duplicate_and_size_logs_file(tempdir)

            # Exclude yaml file generated by manifest_system
            file_list = [f for f in os.listdir(tempdir) if "manifest_system-generated_openshift" not in f]
            # Going over each tar file and base on condition check the expected content.
            for file in file_list:
                if verify_bootstrap_errors and "bootstrap" in file:
                    _verify_bootstrap_logs_uploaded(tempdir, file, installation_success, verify_control_plane)
                elif check_oc and "controller" in file:
                    _verify_oc_logs_uploaded(os.path.join(tempdir, file))
                elif "master" in file or "worker" in file:
                    try:
                        # check master, workers includes bootstrap(master)
                        _verify_node_logs_uploaded(tempdir, file)
                    except tarfile.ReadError as e:
                        log.warning(f"could not verify file {tempdir}/{file} ({e})")


def wait_and_verify_oc_logs_uploaded(cluster, cluster_tar_path):
    try:
        cluster.wait_for_logs_complete(
            timeout=OC_DOWNLOAD_LOGS_TIMEOUT, interval=OC_DOWNLOAD_LOGS_INTERVAL, check_host_logs_only=False
        )
        cluster.download_installation_logs(cluster_tar_path)
        assert os.path.exists(cluster_tar_path), f"{cluster_tar_path} doesn't exist"
        _verify_oc_logs_uploaded(cluster_tar_path)
    except BaseException:
        log.exception("oc logs were not uploaded")
        raise


def verify_logs_are_current(started_cluster_install_at, logs_collected_at):
    for collected_at in logs_collected_at:
        # if host timestamp is set at all- check that the timestamp is from the last installation
        if collected_at > time.time() - 86400000:
            assert collected_at > started_cluster_install_at, (
                f"logs collected at {collected_at}" f" before start time {started_cluster_install_at}"
            )


def verify_logs_not_uploaded(cluster_tar_path, category):
    assert os.path.exists(cluster_tar_path), f"{cluster_tar_path} doesn't exist"

    with TemporaryDirectory() as tempdir:
        with _safe_open_tar(cluster_tar_path, tempdir) as tar:
            log.info(f"downloaded logs: {tar.getnames()}")
            tar.extractall(tempdir)
            assert category not in os.listdir(tempdir), f"{category} logs were found in uploaded logs"


def to_utc(timestr):
    # TODO - temporary import!! Delete after deprecating utils.get_logs_collected_at to avoid cyclic import
    import datetime

    return time.mktime(datetime.datetime.strptime(timestr, "%Y-%m-%dT%H:%M:%S.%fZ").timetuple())


def get_logs_collected_at(client, cluster_id):
    hosts = client.get_cluster_hosts(cluster_id)
    return [to_utc(host["logs_collected_at"]) for host in hosts]


def wait_for_controller_logs(client, cluster_id, timeout, interval=60):
    try:
        # if logs_info has any content, the conroller is alive and healthy
        waiting.wait(
            lambda: client.cluster_get(cluster_id).logs_info,
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="controller logs_info to be filled",
        )
    except BaseException:
        log.exception("Failed to wait on start of controller logs on cluster %s", cluster_id)
        return False


def wait_for_logs_complete(client, cluster_id, timeout, interval=60, check_host_logs_only=False):
    log.info("wait till logs of cluster %s are collected (or timed-out)", cluster_id)
    statuses = ["completed", "timeout"]
    try:
        waiting.wait(
            lambda: _are_logs_in_status(
                client=client, cluster_id=cluster_id, statuses=statuses, check_host_logs_only=check_host_logs_only
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Logs to be in status {statuses}",
        )
        log.info("logs are in expected state")
    except BaseException:
        log.error("waiting for logs expired after %d", timeout)
        raise


def _check_entry_from_extracted_tar(component, tarpath, verify):
    with TemporaryDirectory() as tempdir:
        log.info(f"open tar file {tarpath}")
        with _safe_open_tar(tarpath, tempdir) as tar:
            log.info(f"verifying downloaded logs: {tar.getnames()}")
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


def _verify_node_logs_uploaded(dir_path: str, file_path: str) -> None:
    """Directory file conatains *.tar file - filtered caller
    Extracting tar file to tar.gz file
    Extracting tar.gz to directory
    Accessing files inside the directory
    :param dir_path:
    :param file_path:
    :return:
    """
    with tarfile.open(os.path.join(dir_path, file_path)) as gz:
        # Extract tar file into gz to the same directory
        gz.extractall(path=dir_path)
        tar_gz_file = gz.getnames()
        assert len(tar_gz_file) == 1, f"Expecting for a single tar.gz file {tar_gz_file}"
        tat_gz_file = tar_gz_file[0]

        unpack_tar_gz_dir = os.path.join(dir_path, tat_gz_file.split(".tar.gz")[0])
        # unpacking tar.gz into directory same name without tar.gz
        shutil.unpack_archive(filename=os.path.join(dir_path, tat_gz_file), extract_dir=unpack_tar_gz_dir)
        unpack_log_host_dir = os.listdir(unpack_tar_gz_dir)
        assert len(unpack_log_host_dir) == 1, f"Expecting for a single tar.gz file {unpack_log_host_dir}"
        unpack_log_host_dir = unpack_log_host_dir[0]

        # files inside log_host directory
        log_host_dir = os.path.join(unpack_tar_gz_dir, unpack_log_host_dir)
        log_host_files = os.listdir(log_host_dir)

        # Verify created logs files are not empty
        for file in log_host_files:
            file_name = os.path.join(log_host_dir, file)
            file_size = os.stat(file_name).st_size
            assert (
                file_size > MIN_LOG_SIZE_BYTES
            ), f"file {file_name} size is empty with size smaller than {MIN_LOG_SIZE_BYTES}"

        # Verify all expected logs are in the directory
        expected_log_files = ["agent.logs", "installer.logs", "mount.logs", "report.logs"]
        expected_log_files.append("bootkube.logs") if "bootstrap" in file_path else expected_log_files
        assert set(expected_log_files) == set(log_host_files)


def _verify_bootstrap_logs_uploaded(dir_path, file_path, installation_success, verify_control_plane=False):
    with _safe_open_tar(os.path.join(dir_path, file_path), dir_path) as gz:
        logs = gz.getnames()
        assert any("bootkube.logs" in s for s in logs), f"bootkube.logs isn't found in {logs}"
        if not installation_success:
            for logs_type in ["dmesg.logs", "log-bundle"]:
                assert any(logs_type in s for s in logs), f"{logs_type} isn't found in {logs}"
            # test that installer-gather gathered logs from all masters
            lb_path = [s for s in logs if "log-bundle" in s][0]
            gz.extract(lb_path, dir_path)
            with _safe_open_tar(os.path.join(dir_path, lb_path), dir_path) as log_bundle:
                log_bundle.extractall(dir_path)
                cp_path = [s for s in log_bundle.getnames() if "control-plane" in s][0]
                # if bootstrap able to ssh to other masters, test that control-plane directory is not empty
                if verify_control_plane:
                    cp_full_path = os.path.join(dir_path, cp_path)
                    master_dirs = os.listdir(cp_full_path)
                    assert len(master_dirs) == NUMBER_OF_MASTERS - 1, (
                        f"expecting {cp_full_path} to have " f"{NUMBER_OF_MASTERS - 1} values"
                    )
                    log.info(f"control-plane directory has sub-directory for each master: {master_dirs}")
                    for ip_dir in master_dirs:
                        log.info(f"{ip_dir} content: {os.listdir(os.path.join(cp_full_path, ip_dir))}")
                        assert len(os.listdir(os.path.join(cp_full_path, ip_dir))) > 0, f"{cp_path}/{ip_dir} is empty"


def _are_logs_in_status(client, cluster_id, statuses, check_host_logs_only=False):
    try:
        cluster = client.cluster_get(cluster_id)
        hosts = client.get_cluster_hosts(cluster_id)
        cluster_logs_status = cluster.logs_info
        host_logs_statuses = [host.get("logs_info", "") for host in hosts]
        if all(s in statuses for s in host_logs_statuses) and (
            check_host_logs_only or (cluster_logs_status in statuses)
        ):
            log.info("found expected state. cluster logs: %s, host logs: %s", cluster_logs_status, host_logs_statuses)
            return True

        log.info(
            "Cluster logs not yet in their required state. %s, host logs: %s", cluster_logs_status, host_logs_statuses
        )
        return False
    except BaseException:
        log.exception("Failed to get cluster %s log info", cluster_id)
        return False


def filter_controllers_logs(client, cluster_id, filters, last_messages=10):
    """Get controller log file when possible when master's in finalized stage and filter messages.

    Used to detect error or warning when timeout expires , will be added to the exception last known errors/warning
    :param client:
    :param cluster_id:
    :param filters: list of string to match from assisted
    :param last_messages:
    :return:
    """
    installer_controller = 'assisted-installer-controller.logs'
    tmp_file = f"/tmp/{''.join(random.choice(ascii_lowercase) for _ in range(10))}.tar.gz"
    filtered_content = []
    try:
        log.info(f"Collecting controllers info from {installer_controller}")
        controller_data = client.v2_download_cluster_logs(cluster_id, logs_type="controller",
                                                          _preload_content=False).data
        with open(tmp_file, "wb") as _file:
            log.info(f"Write controllers content to file {tmp_file}")
            _file.write(controller_data)

        with tarfile.open(tmp_file, 'r') as tar:
            log.info(f"Extract {tmp_file} and create object content")
            content = tar.extractfile(installer_controller).readlines()
            reversed_iterator = reversed(content)
            content_lines = [(next(reversed_iterator).decode("utf-8")) for _ in range(last_messages)]

            # filtered content - check if one of the filters in a line
            log.info(f"Searching filters in object content {content_lines}")
            for line in content_lines:
                for f in filters:
                    if f in line:
                        filtered_content.append(line)

    except ApiException as api_error:
        log.info("Failed to get controller logs %s", api_error)

    except Exception as e:
        log.info("Error during controller log filtering %s", str(e))
    finally:
        try:
            os.remove(tmp_file)
        except FileNotFoundError:
            log.info("Unable to remove tmp file %s", tmp_file)
        return filtered_content
