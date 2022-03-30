FROM quay.io/cchun/python:3.9.12-alpine3.15

ARG SERVER_IP
ARG SERVER_PORT
ENV SERVER_IP=${SERVER_IP}
ENV SERVER_PORT=${SERVER_PORT}

COPY . .

CMD [ "python", "./local_ipxe_server.py" ]
