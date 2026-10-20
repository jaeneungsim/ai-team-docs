"""Where the sync keeps its work: one DynamoDB table and one S3 bucket.

Table items (pk, sk):
    PAGE, <page id>   one indexed page: version, title, link, S3 keys, chunk count, flags
    STATE, STATE      the current index build, the last run, the last successful sync, usage
    LOCK, LOCK        the run lock, which stops counting after `expires_at`

Bucket keys:
    raw/<page>/<version>.xhtml     the storage format as Confluence sent it
    md/<page>/<version>.md         the converted Markdown
    chunks/<page>/<version>.json   the chunks, each with a hash of the text that was embedded
    vectors/<page>/<version>.npy   one embedding per chunk
    index/<build>/                 a search index: index.sqlite and vectors.npy

Files nothing uses any more (a page's old version, a removed page, a replaced index build) are
tagged superseded=true, and a bucket lifecycle rule deletes a tagged file once it is a week old.
The sync itself may not delete objects.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from . import aws
from .env import required

STATE_KEY = {"pk": "STATE", "sk": "STATE"}
LOCK_KEY = {"pk": "LOCK", "sk": "LOCK"}


class Store:
    def __init__(self, table: Any, s3: Any, bucket: str):
        self._table = table
        self._s3 = s3
        self._bucket = bucket

    @classmethod
    def from_env(cls) -> Store:
        return cls(aws.table(required("TABLE_NAME")), aws.client("s3"), required("BUCKET_NAME"))

    # --- run lock ---------------------------------------------------------------------------------

    def acquire_lock(self, owner: str, now: int, seconds: int) -> bool:
        """Take the lock unless another run holds one that has not expired."""
        try:
            self._table.put_item(
                Item={**LOCK_KEY, "owner": owner, "expires_at": now + seconds},
                ConditionExpression="attribute_not_exists(pk) OR expires_at < :now",
                ExpressionAttributeValues={":now": now},
            )
            return True
        except Exception as err:
            if aws.error_code(err) == "ConditionalCheckFailedException":
                return False
            raise

    def release_lock(self, owner: str) -> None:
        try:
            self._table.delete_item(
                Key=LOCK_KEY,
                ConditionExpression="#owner = :owner",
                ExpressionAttributeNames={"#owner": "owner"},
                ExpressionAttributeValues={":owner": owner},
            )
        except Exception as err:
            if aws.error_code(err) != "ConditionalCheckFailedException":
                raise

    # --- pages and state --------------------------------------------------------------------------

    def pages(self) -> dict[str, dict[str, Any]]:
        """Every PAGE item by page id. Read consistently, so pages written in this run are included."""
        items: list[dict[str, Any]] = []
        query: dict[str, Any] = {
            "KeyConditionExpression": "pk = :pk",
            "ExpressionAttributeValues": {":pk": "PAGE"},
            "ConsistentRead": True,
        }
        while True:
            answer = self._table.query(**query)
            items.extend(answer["Items"])
            if "LastEvaluatedKey" not in answer:
                break
            query["ExclusiveStartKey"] = answer["LastEvaluatedKey"]
        return {item["sk"]: _plain(_without_keys(item)) for item in items}

    def put_page(self, page: dict[str, Any]) -> None:
        self._table.put_item(Item={"pk": "PAGE", "sk": page["page_id"], **page})

    def delete_page(self, page_id: str) -> None:
        self._table.delete_item(Key={"pk": "PAGE", "sk": page_id})

    def state(self) -> dict[str, Any]:
        item = self._table.get_item(Key=STATE_KEY, ConsistentRead=True).get("Item") or {}
        return _plain(_without_keys(item))

    def put_state(self, state: dict[str, Any]) -> None:
        self._table.put_item(Item={**STATE_KEY, **state})

    # --- objects ----------------------------------------------------------------------------------

    def put(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def upload(self, path: Path, key: str) -> None:
        self._s3.upload_file(str(path), self._bucket, key)

    def download(self, key: str, path: Path) -> None:
        self._s3.download_file(self._bucket, key, str(path))

    def mark_superseded(self, keys: list[str]) -> None:
        """Tag files nothing uses any more; a bucket lifecycle rule deletes a tagged file once it is a week old."""
        for key in keys:
            self._s3.put_object_tagging(
                Bucket=self._bucket, Key=key, Tagging={"TagSet": [{"Key": "superseded", "Value": "true"}]}
            )


def _without_keys(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in ("pk", "sk")}


def _plain(value: Any) -> Any:
    """DynamoDB returns numbers as Decimal; the rest of the code uses int."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value
