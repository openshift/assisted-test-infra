FROM quay.io/assisted-installer-ops/base-python:3.12

ARG SERVER_IP
ARG SERVER_PORT
ENV SERVER_IP=${SERVER_IP}
ENV SERVER_PORT=${SERVER_PORT}

COPY . .

CMD [ "python", "./local_ipxe_server.py" ]
