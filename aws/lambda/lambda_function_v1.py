import json
def lambda_handler(event, context):
    records = event.get("Records", [])
    for record in records:
        incident = json.loads(record["body"])
        print(json.dumps({
            "message_id": record["messageId"],
            "incident_id": incident.get("incident_id"),
            "event": incident.get("event"),
            "source": incident.get("source"),
            "timestamp": incident.get("timestamp")
        }))
    return {"processed": len(records)}
