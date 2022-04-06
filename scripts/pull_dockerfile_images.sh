#!/bin/bash

export CONTAINER_COMMAND=${CONTAINER_COMMAND:-podman}

images=$(cat Dockerfile.* ./*/Dockerfile.* | grep -i FROM | awk '{print $2}')
images=${images//--from=}

echo "### Attempting to pull assisted dockerfile images (best effort) ###"
echo "Images found: ${images}"

for image in ${images}; do
  if [[ ${image} =~ (.*\/.*:.*) ]]; then
      for i in {1..5}; do
        echo "Image ${image} - pull attempt ${i}"
        podman pull "${image}" ; rc=$?
        if [[ "${rc}" -eq 0 ]]; then
          echo "Image pulled successfully"
          break
        fi

        echo "Failed to pull image ${image}"
        if [[ "${i}" -ne 5 ]]; then
          echo "Retrying ..."
          sleep 5
        fi

      done
  fi
done
