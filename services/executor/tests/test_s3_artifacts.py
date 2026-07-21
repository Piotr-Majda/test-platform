from test_platform_executor.framework.artifacts import S3ArtifactStore


class _FakeS3:
    def __init__(self) -> None:
        self.upload = None

    def put_object(self, **kwargs) -> None:
        self.upload = kwargs


def test_s3_store_uploads_and_returns_portable_reference() -> None:
    client = _FakeS3()
    store = S3ArtifactStore("test-artifacts", "run-1", client)

    artifact = store.write_text("step/test.log.json", '{"ok":true}', "application/json")

    assert client.upload == {
        "Bucket": "test-artifacts",
        "Key": "run-1/step/test.log.json",
        "Body": b'{"ok":true}',
        "ContentType": "application/json",
    }
    assert artifact.relative_path == "run-1/step/test.log.json"
    assert artifact.name == "test.log.json"
