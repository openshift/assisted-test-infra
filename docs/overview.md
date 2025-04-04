# Test-Infra

The `assisted-test-infra` project provides a comprehensive framework for testing the OpenShift Assisted Installer in a simulated bare-metal environment. It uses libvirt-based virtual machines to emulate physical hosts, enabling realistic end-to-end testing workflows for OpenShift cluster installation.

This project is primarily used for development, CI, and QE purposes. It includes Makefile targets and utility scripts to automate deployment, testing, and cleanup tasks.

The framework is built around `pytest`: execution flows are structured as tests, and the various operations needed to reach those test goals are implemented as fixtures.