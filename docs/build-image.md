# Build Image

This project uses `skipper` for executing some of its operations inside containers. It is configured to work with an already built image `assisted-test-infra:latest`. To build the image, run:

```bash
make image_build
```

the building of the image is automatically executed during the [setup](./setup.md).

## Adjusting the python client

For building this image, a valid [python client package](./assisted-service-client.md) is required. For building the image with specific client, see [these](./assisted-service-client.md#rebuilding-the-client-with-the-build-image) instructions. 