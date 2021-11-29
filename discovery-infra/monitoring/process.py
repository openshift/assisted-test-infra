import re
import json
import logging
import collections

REMOVED_FIELDS = [
    "cluster.image_info_ssh_public_key",
    "cluster.ssh_public_key",
    "cluster.image_info.ssh_public_key"
    "cluster.connectivity_majority_groups",
    "cluster.controller_logs_collected_at",

    "cluster.hosts.connectivity",
    "cluster.hosts.images_status",

    "cluster.image_info_download_url",
    "cluster.image_info_expires_at",
    "cluster.image_info_size_bytes",
    "cluster.ingress_vip",
    "link"
]

SKIPPABLE_EVENTS = [
    "reached installation stage Writing image to disk"
]

logging.basicConfig(level=logging.WARN, format='%(levelname)-10s %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("__main__").setLevel(logging.INFO)

class GetProcessedMetadataJson:

    def __init__(self, metadata_json):
        self.metadata_json = metadata_json
        self.__convert_strings_to_dict()
        self.__set_host_vendor()

    def get_processed_json(self):
        self.__remove_fields_if_exists()
        return self.metadata_json

    def __set_host_vendor(self):
        for host in self.metadata_json["cluster"]["hosts"]:
            if "inventory" not in host:
                return
            inventory = json.loads(host["inventory"])
            vendor = inventory.get("system_vendor", None)
            if vendor:
                host["vendor"] = vendor


    def __convert_strings_to_dict(self):
        if "validations_info" in self.metadata_json["cluster"]:
            self.metadata_json["cluster"]["validations_info"] = convert_field_to_json(self.metadata_json["cluster"]["validations_info"])

        if "feature_usage" in self.metadata_json["cluster"]:
            feature_usage = convert_field_to_json(self.metadata_json["cluster"]["feature_usage"])
            self.metadata_json["cluster"]["feature_usage"] = [feature_usage[feature] for feature in feature_usage]

        for host in self.metadata_json["cluster"]["hosts"]:
            if host.get("validations_info", None):
                host["validations_info"] = convert_field_to_json(host["validations_info"])

    def __remove_fields_if_exists(self):
        for remove_field in REMOVED_FIELDS:
            try:
                self.__pop_fields(self.metadata_json, remove_field)
            except KeyError:
                pass

    # Delete a field in string path joind by "."
    def __pop_fields(self, p_json, pop_str):
        if type(p_json) == list:
            for l in p_json:
                self.__pop_fields(l, pop_str)
            return
        pop_list = pop_str.split(".", 1)
        if len(pop_list) == 1:
            del p_json[pop_list[0]]
            return
        if pop_list[0] not in p_json:
            return
        self.__pop_fields(p_json[pop_list[0]], pop_list[1])
        return

def is_event_skippable(event):
    for skippable_text in SKIPPABLE_EVENTS:
        if skippable_text in event["message"]:
            return True
    return False

def convert_field_to_json(converted_field):
    try:
        if type(converted_field) == str:
            return json.loads(converted_field)
    except KeyError:
        logger.warning("Error while conversing to json")
