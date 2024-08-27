import logging
from random import randint

import openshift_client as oc
import pytest
import waiting
from jinja2 import Environment, PackageLoader
from junit_report import JunitTestSuite

from assisted_test_infra.test_infra import utils
from consts import resources
from tests.base_test import BaseTest

log = logging.getLogger(__name__)
curl_script = (
    "https://raw.githubusercontent.com/openshift/assisted-service/master/docs/user-guide/day2-master/"
    "link-machine-and-node.sh"
)
script_file = "/tmp/link-machine-and-node.sh"


class TestClusterScaleUp(BaseTest):
    @staticmethod
    def _apply_yaml_file(
        yaml_file,
        package_name="tests",
        package_path="templates",
        project="default",
        **kwargs_yaml,
    ):
        """

        :param yaml_file: yaml j2 file from template directory
        :param package_name:  main directory
        :param package_path: template patch
        :param project:
        :param kwargs_yaml:  set the yaml params example: master_host_name=vm_volume_mode
        :return:
        """

        env = Environment(loader=PackageLoader(package_name, package_path))
        template = env.get_template(yaml_file)

        with oc.project(project):
            yaml_object = template.render(**kwargs_yaml)
            log.info(f"Applying the '{yaml_object}' on project '{project}'")
            oc.apply(yaml_object, auto_raise=True)

    @pytest.fixture()
    def download_script(self):
        redirect = f" -o {script_file}"
        command = f"curl {curl_script} {redirect}"
        cmd_out, _, _ = utils.run_command(command, shell=True)
        log.info(f"Download script {cmd_out}")
        chmod_out, _, _ = utils.run_command(f"chmod 755 {script_file}", shell=True)
        log.info(f"chmod script {chmod_out}")
        yield
        log.info(f"Deleting script {script_file}")
        utils.run_command(f"rm -rf {script_file}", shell=True)

    @staticmethod
    def _run_scripts(the_script_file, *args):
        command = f'{the_script_file} {" ".join(args)}'
        cmd_out, _, _ = utils.run_command(command, shell=True)
        log.info(f"run script {cmd_out}")

    @staticmethod
    def _format_node_disk(the_node):
        # format the node disk - two disks iso and bootable
        storage_path = the_node.node_controller.get_all_vars()["storage_pool_path"]
        disk_info = [
            f"{disk.source_pool}/{disk.source_volume}"
            for disk in the_node.get_disks()
            if disk.type == "disk" and disk.source_pool and disk.source_volume
        ]
        assert len(disk_info) == 1
        the_node.node_controller.format_disk(storage_path + "/" + disk_info[0])

    @staticmethod
    def _set_master_role(day2_cluster):
        # we re-use worker node from day1 cluster, setting the role to master for day2
        host = day2_cluster.to_cluster_hosts(day2_cluster.api_client.get_cluster_hosts(day2_cluster.id))[0]
        day2_cluster._infra_env.update_host(host_id=host.get_id(), host_role="master", host_name=host.get_hostname())

    @staticmethod
    def _delete_ocp_node(the_node):
        # delete the worker node from ocp because installing it as day2 master
        with oc.project("default"):
            node_obj = oc.selector(f"nodes/{the_node.name}").objects()
            assert len(node_obj) == 1, "Expecting for a single node"
            node_obj[0].delete()

    @staticmethod
    def _wait_for_etcd_status_available(project, obj_name, message):
        def _is_etcd_members_available(the_project=project, the_message=message):
            with oc.project(the_project):
                try:
                    etcd_obj = oc.selector(obj_name).object()
                    message_returned = [
                        v for v in etcd_obj.model.status.conditions if v.get("message") and the_message in v["message"]
                    ]
                    return True if len(message_returned) == 1 else False
                except oc.OpenShiftPythonException as e:
                    log.debug(f"Unable to read object {str(e)}")
                return False

        log.info(f"Checking if {message}")
        waiting.wait(
            lambda: _is_etcd_members_available(),
            timeout_seconds=900,
            sleep_seconds=30,
            waiting_for="etcd members are Available",
        )

    @JunitTestSuite()
    @pytest.mark.parametrize("day2_workers_count", [0])
    @pytest.mark.parametrize("worker_disk", [resources.DEFAULT_MASTER_DISK])
    @pytest.mark.parametrize("worker_vcpu", [resources.DEFAULT_MASTER_CPU])
    @pytest.mark.parametrize("worker_memory", [resources.DEFAULT_MASTER_MEMORY])
    def test_ctlplane_scaleup(
        self,
        day2_cluster,
        cluster,
        day2_workers_count,
        worker_disk,
        worker_vcpu,
        worker_memory,
        download_script,
    ):
        """Day2 for master nodes.

        Install day1 cluster with 3 masters and workers with more cpu and memory and disk size.
        This test will not run in the regressions marker, its helper for etcd team to create more masters above 3.
        # https://redhat-internal.slack.com/archives/CH76YSYSC/p1723136720052059
        This test will support to create additional masters in day2 post deployment , we can have 5 , 7 ...
        At the end of the test we verified all masters joined as etcd members.

        #configure env params:
        # We re-use workers and create day2 masters. WORKERS_COUNT  must eq to NUM_DAY2_MASTERS
        export NUM_DAY2_MASTERS=2
        export WORKERS_COUNT=2
        export TEST_TEARDOWN=false
        export OPENSHIFT_VERSION=4.17
        export TEST_FUNC=test_create_day2_masters

        # run the test
        make test

        """

        new_nodes_count = cluster.nodes.masters_count + day2_cluster._config.day2_masters_count

        self.update_oc_config(nodes=cluster.nodes, cluster=cluster)
        cluster.download_kubeconfig()

        # Install day2
        log.info(f"Scaling up OCP cluster {cluster.name} with {new_nodes_count} nodes")
        day2_image_path = "/tmp/day2_image" + str(randint(1, 2000)) + ".iso"
        day2_cluster.generate_and_download_infra_env(iso_download_path=day2_image_path)
        reused_workers = []
        for worker in cluster.nodes.get_workers():
            reused_workers.append(worker)
            worker.shutdown()
            worker.set_boot_order(cd_first=False, cdrom_iso_path=day2_image_path)
            self._format_node_disk(worker)
            worker.start()

        utils.run_command(f"rm -rf {day2_image_path}", shell=True)
        # bind the node to day2_cluster
        day2_cluster.nodes._nodes = [*reused_workers]
        day2_cluster.wait_until_hosts_are_discovered()

        for host_worker in day2_cluster.to_cluster_hosts(day2_cluster.api_client.get_cluster_hosts(day2_cluster.id)):
            day2_cluster._infra_env.update_host(
                host_id=host_worker.get_id(), host_role="master", host_name=host_worker.get_hostname()
            )

        # delete the worker node from ocp because installing them as master role
        for re_use_worker in reused_workers:
            self._delete_ocp_node(re_use_worker)

        day2_cluster.start_install_and_wait_for_installed()

        log.info(f"{new_nodes_count} master nodes were successfully added to OCP cluster")
        # applying day2 nodes into yaml
        for worker in reused_workers:
            baremetal_host_name = "custom-" + worker.name
            self._apply_yaml_file("day2_baremetal.yaml.j2", master_host_name=baremetal_host_name)
            self._apply_yaml_file(
                "day2_machine.yaml.j2", master_host_name=baremetal_host_name, cluster_name=cluster.name
            )
            self._run_scripts(script_file, baremetal_host_name, worker.name)
        # verify etcd members updated and available
        self._wait_for_etcd_status_available(
            project="default", obj_name="etcd", message=f"{new_nodes_count} members are available"
        )
