# Assisted Service Client

The Assisted Service project generates a Python client package using `swagger-codegen-cli` whenever a new commit is merged into the `master` branch. This package is built and published to PyPI.

This project uses that Python client to interact with the Assisted Service once it is deployed. In some use cases, the client must be compatible with the specific Assisted Service image in use (testing API changes, etc.). To ensure compatibility, the client is installed as part of the [build image](./build-image.md), which uses the client during test execution.

Since the client code must match the deployed Assisted Service code, it is not possible to use an appropriate client when deploying a different service image via `SERVICE=...`.

### Rebuilding the Client with the build image

To ensure you are using a matching client version, rebuild the [build image](./build-image.md) **before** deploying Assisted Service by running:

```bash
make image_build SERVICE_REPO=<assisted-service repository to use> SERVICE_BASE_REF=<assisted-service branch to use>
```

This code:

    1. Brings assisted service repo/branch you specified.
    2. Builds the python client from it.
    3. builds the build image with this client.
