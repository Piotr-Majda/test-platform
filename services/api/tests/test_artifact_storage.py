from io import BytesIO

from test_platform_api.artifact_storage import LocalArtifactStorage, S3ArtifactStorage


class _Paginator:
    def paginate(self, **kwargs):
        prefix = kwargs["Prefix"]
        return [{"Contents": [{"Key": key} for key in _FakeS3.objects if key.startswith(prefix)]}]


class _FakeS3:
    objects: dict[str, bytes] = {}

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key])}

    def head_object(self, *, Bucket, Key):
        return {"ContentLength": len(self.objects[Key])}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return _Paginator()

    def delete_objects(self, *, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)


def test_local_storage_rejects_path_traversal(tmp_path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    try:
        storage.read_bytes("../secret")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal must be rejected")


def test_s3_storage_reads_lists_and_deletes_prefix() -> None:
    _FakeS3.objects = {
        "run-1/test-a/test.log.json": b'{"ok":true}',
        "run-1/step/page.html": b"<html></html>",
    }
    storage = S3ArtifactStorage("artifacts", _FakeS3())

    assert storage.read_bytes("run-1/test-a/test.log.json") == b'{"ok":true}'
    assert storage.size("run-1/test-a/test.log.json") == 11
    assert sorted(storage.list_keys("run-1")) == sorted(_FakeS3.objects)
    assert storage.delete_prefix("run-1") == 1
    assert storage.list_keys("run-1") == []
