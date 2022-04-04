#!/bin/bash

export CONTAINER_COMMAND=${CONTAINER_COMMAND:-podman}

images=$(cat Dockerfile.* ./*/Dockerfile.* | grep FROM | awk '{print $2}')
echo "### Attempting to download assisted dockerfile images (best effort) ###"
echo "Images found: ${images}"

for image in ${images}; do
  if [[ ${image} =~ (.*:.*) ]]; then
      for i in {1..5}; do
        echo "Image ${image} ${i} download attempt ${image}"
        podman pull "${image}" || rc=$?

        if [[ "${rc}" -eq 0 ]]; then
          break
        fi

        echo "Failed to download image ${image}, retrying ..."
      done
  fi
done
