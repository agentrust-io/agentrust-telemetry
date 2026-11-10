"""Pure observer assertions; local acceptance, attempts and commits stay distinct."""
import json


def any_value(value):
    kind = value.WhichOneof("value")
    if kind == "kvlist_value":
        return {item.key: any_value(item.value) for item in value.kvlist_value.values}
    if kind == "array_value":
        return [any_value(item) for item in value.array_value.values]
    if kind in {"string_value", "bool_value", "int_value", "double_value"}:
        return getattr(value, kind)
    raise ValueError(f"unsupported normalized-event value {kind}")


def check_projection(events, observations):
    expected = {event["event_id"]: event for event in events}
    if not observations:
        raise AssertionError("no independent projection observations")
    for observation in observations:
        event = observation["body"]
        original = expected[event["event_id"]]
        if json.dumps(event, sort_keys=True, allow_nan=False) != json.dumps(original, sort_keys=True, allow_nan=False):
            raise AssertionError("normalized event body changed")
        if observation["event_name"] != original["event_type"]:
            raise AssertionError("event name changed")
        if observation["timestamp_ns"] != original["time_unix_nano"]:
            raise AssertionError("event timestamp changed")


def check_delivery(mode, events, evidence_count, attempts, commits):
    ids = [event["event_id"] for event in events]
    if evidence_count != len(events):
        raise AssertionError("local evidence is missing")
    if not set(commits).issubset(ids) or not set(attempts).issubset(ids):
        raise AssertionError("observer saw an unsubmitted event")
    if mode == "queue_saturation":
        if not 0 < len(set(commits)) < len(events):
            raise AssertionError("expected bounded queue loss was not independently observed")
    elif set(commits) != set(ids):
        raise AssertionError("a submitted event did not commit")
    if mode == "reorder":
        times = [int(event["time_unix_nano"]) for event in events]
        if len(times) < 2 or not all(left > right for left, right in zip(times, times[1:])):
            raise AssertionError("reorder control did not submit descending timestamps")
        if set(attempts) != set(ids):
            raise AssertionError("a reordered input was not independently observed")
        # Concurrent SDK exports/HTTP requests need not preserve arrival order.
        # check_projection binds every observed timestamp and body to its event ID.
