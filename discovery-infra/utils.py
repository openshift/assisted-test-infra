import subprocess
import shlex
from retry import retry


def run_command(command, shell=False):
    command = command if shell else shlex.split(command)
    process = subprocess.run(command, shell=shell, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout.strip()
    return output


def run_command_with_output(command):
    with subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


@retry(tries=5, delay=3, backoff=2)
def get_service_url(service_name):
    print("Getting inventory url")
    cmd = "minikube service %s --url" % service_name
    return run_command(cmd)
