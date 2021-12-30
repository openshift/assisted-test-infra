import argparse

from .virsh_cleanup import DEFAULT_SKIP_LIST, clean_virsh_resources, log


def _get_parsed_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear libvrt resources")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-a", "--all", help="Clean all virsh resources", action="store_true")
    group.add_argument("-m", "--minikube", help="Clean only minikube resources", action="store_true")
    group.add_argument("--skip-minikube", help="Clean all but skip minikube resources", action="store_true")
    group.add_argument(
        "-f",
        "--filter",
        help="List of filter of resources to delete",
        nargs="*",
        type=str,
        default=None,
    )
    return parser.parse_args()


def main():
    log.info("===== CLEANING VIRSH RESOURCES =====")
    p_args = _get_parsed_args()
    skip_list = DEFAULT_SKIP_LIST
    resource_filter = []
    if p_args.minikube:
        resource_filter.append("minikube")
    elif p_args.filter:
        resource_filter = p_args.filter
    else:
        skip_list.extend(["minikube", "minikube-net"])

    clean_virsh_resources(skip_list, resource_filter)


if __name__ == "__main__":
    main()
