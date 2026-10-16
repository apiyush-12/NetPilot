import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get(
    "NETPILOT_TABLE",
    "netpilot-events-dev"
)

table = boto3.resource("dynamodb").Table(TABLE_NAME)


def lambda_handler(event, context):
    written = 0
    duplicates = 0

    for record in event.get("Records", []):
        # Decimal preserves JSON floating-point values
        # for DynamoDB serialization.
        incident = json.loads(
            record["body"],
            parse_float=Decimal
        )

        if not isinstance(incident, dict):
            raise ValueError("Incident must be a JSON object")

        event_id = incident.get("event_id")

        # Compatibility with older test messages
        # that do not contain an event_id.
        if not isinstance(event_id, str) or not event_id:
            event_id = record["messageId"]

        now = datetime.now(timezone.utc).isoformat()

        item = {
            "event_id": event_id,
            "event_type": str(
                incident.get("event", "UNKNOWN")
            ),
            "source": str(
                incident.get("source", "netpilot-agent")
            ),
            "timestamp": str(
                incident.get("timestamp") or now
            ),
            "received_at": now,
            "sqs_message_id": record["messageId"],
            "payload": incident
        }

        if incident.get("incident_id") is not None:
            item["incident_id"] = str(
                incident["incident_id"]
            )

        try:
            table.put_item(
                Item=item,
                ConditionExpression=(
                    "attribute_not_exists(event_id)"
                )
            )

            written += 1

            print(json.dumps({
                "event": "DB_WRITE_SUCCESS",
                "event_id": event_id,
                "table": TABLE_NAME
            }))

        except ClientError as error:
            error_code = error.response["Error"]["Code"]

            if error_code == "ConditionalCheckFailedException":
                duplicates += 1

                print(json.dumps({
                    "event": "DUPLICATE_EVENT_SKIPPED",
                    "event_id": event_id
                }))
            else:
                raise

    return {
        "processed": len(event.get("Records", [])),
        "written": written,
        "duplicates": duplicates
    }