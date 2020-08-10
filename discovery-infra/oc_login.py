import os
import yaml

from logger import log
from utils import run_command


def oc_login(token=None, server=None):
    log.info('Performing oc-login')
    cmd = _get_cmd(token, server)
    run_command(cmd)


def _get_cmd(token, server):
    if not token or not server:
        token, server = _find_token_and_server_from_kubeconfig()

    return _build_cmd_from_token_and_server(token, server)


def _find_token_and_server_from_kubeconfig():
    config = _load_kubeconfig()
    for cluster in _iterate_clusters(config):
        user = _get_user_by_cluster(config, cluster)
        if not user:
            continue
        token = _get_token_by_user(config, user)
        if not token:
            continue
        server = cluster['cluster']['server']
        return token, server

    raise RuntimeError(
        'unable to find any valid pair of token and server in kubeconfig file '
        'to perform oc-login'
    )


def _load_kubeconfig():
    config_file = os.path.join(os.environ['HOME'], '.kube', 'config')
    with open(config_file) as fp:
        return yaml.safe_load(fp)


def _iterate_clusters(config):
    clusters = config.get('clusters', [])
    if len(clusters) == 0:
        raise RuntimeError(f'no clusters found in config: {config}')

    for c in clusters:
        yield c


def _get_user_by_cluster(config, cluster):
    for ctx in config['contexts']:
        if ctx['context']['cluster'] == cluster['name']:
            return ctx['context']['user']


def _get_token_by_user(config, user):
    for u in config['users']:
        if u['name'] == user and 'token' in u['user']:
            return u['user']['token']


def _build_cmd_from_token_and_server(token, server):
    return 'oc login ' \
           '--insecure-skip-tls-verify=true ' \
           f'--token={token} ' \
           f'--server={server}'
