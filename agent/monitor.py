import subprocess
import time
import json
from datetime import datetime, timezone

PROJECT_DIR = r"A:\NetPilot\lab"
DESTINATION = "10.66.2.10"

CHECK_INTERVAL = 5
FAILURE_THRESHOLD = 3


def docker_exec(service, *args):
    command = [
        "docker", "compose",
        "--project-directory", PROJECT_DIR,
        "exec", "-T", service, *args
    ]

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=15
    )


def log_event(event_type, **details):
    event = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": event_type,
        **details
    }
    print(json.dumps(event), flush=True)


def check_connectivity():
    result = docker_exec(
        "client", "ping",
        "-c", "1", "-W", "2",
        DESTINATION
    )
    return result.returncode == 0


def check_backup():
    result = docker_exec(
        "client", "ping",
        "-c", "1", "-W", "2",
        "10.66.1.3"
    )
    return result.returncode == 0


def switch_to_backup():
    client = docker_exec(
        "client", "ip", "route", "replace",
        "10.66.2.0/24", "via", "10.66.1.3"
    )

    server = docker_exec(
        "server", "ip", "route", "replace",
        "10.66.1.0/24", "via", "10.66.2.3"
    )

    return (
        client.returncode == 0
        and server.returncode == 0
    )


def main():
    failures = 0
    recovery_attempted = False

    log_event("MONITOR_STARTED")

    while True:
        try:
            if check_connectivity():
                failures = 0
                log_event("NETWORK_HEALTHY")

            else:
                failures += 1
                log_event(
                    "CONNECTIVITY_FAILURE",
                    consecutive_failures=failures
                )

                if (
                    failures >= FAILURE_THRESHOLD
                    and not recovery_attempted
                ):
                    recovery_attempted = True

                    if not check_backup():
                        log_event("BACKUP_UNAVAILABLE")
                        continue

                    log_event("RECOVERY_STARTED")

                    if switch_to_backup():
                        time.sleep(2)

                        if check_connectivity():
                            log_event("RECOVERY_SUCCESS")
                        else:
                            log_event(
                                "RECOVERY_VERIFICATION_FAILED"
                            )
                    else:
                        log_event("ROUTE_UPDATE_FAILED")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log_event("MONITOR_STOPPED")
            break

        except Exception as error:
            log_event(
                "MONITOR_ERROR",
                error=str(error)
            )
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()