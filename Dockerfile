FROM quay.io/app-sre/centos:8

RUN dnf install -y testdisk

CMD ["testdisk"]
