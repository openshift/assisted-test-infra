#!/bin/bash
set -euo pipefail

GO_VERSION="${GO_VERSION:-1.17.4}"

function install_golang() {
    if ! [ -x "$(command -v go)" ]; then
        echo "Installing golang..."
        curl -s https://storage.googleapis.com/golang/go"$GO_VERSION".linux-amd64.tar.gz | tar -C /usr/local -xz
        echo "successfully installed golang!"
    else
        echo "golang is already installed"
    fi
}

install_golang
export GOPATH=/go
export GOCACHE=/go/.cache
export PATH=$PATH:/usr/local/go/bin:/go/bin