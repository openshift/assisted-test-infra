# KEXEC

This folder contains a script that can use SSH to connect to an existing machines (e.g. where a cluster is already deployed) and boot them into discovery mode.
I Found it useful on bare metal, where virtual media is slow (or doesn't exists) and customizing pxe configuration is a pain.
in theory, this can work on any machine with an OS on existing public clouds (e.g. packet, AWS BM etc)

## Usage

1. Create a new cluster using the assisted installer
2. Configure your download ISO and copy its link
3. On some machine, where you have ssh access to the hosts, execute:

```bash
ISO_URL=<url from above> ./install-cluster.sh hostA hostB hostC ...
```

4. Machines should appear in the assisted installer UI and you could continue with regular installation.
