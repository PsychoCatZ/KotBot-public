"""Kater's view of shared apartment events."""
import json
import re

EPISODES = ("meeting", "box", "broken_box", "repair")
TOPIC = re.compile(r"\b(?:ильз\w*|кошк\w*|соседк\w*|коробк\w*|квартир\w*|скотч\w*)\b", re.I)


def impressions(state, speaker):
    return state.get("relationship_observations", {}).get(speaker, [])[-12:]


def record_impression(state, speaker, evidence, note):
    if evidence is None:
        return
    try:
        observation = json.loads(note)
    except ValueError:
        return
    if not isinstance(observation, dict):
        return
    kind, view = observation.get("kind"), observation.get("view")
    if kind not in ("kept_word", "mistake", "helped", "respected_boundary") or not isinstance(view, str):
        return
    view = view.strip()
    if not view or len(view) > 350:
        return
    records = state.setdefault("relationship_observations", {}).setdefault(speaker, [])
    if any(item["scene"] == evidence["scene"] and item["index"] == evidence["index"] for item in records):
        return
    records.append({**evidence, "kind": kind, "view": view})


def kater_context(conn, text):
    if not TOPIC.search(text):
        return None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='apartment'").fetchone():
        return None
    row = conn.execute("SELECT state FROM apartment WHERE id=1").fetchone()
    if row is None:
        return None
    state = json.loads(row[0])
    journal = {name: state["archive"][name] for name in EPISODES if name in state["archive"]}
    if state.get("scene") in (*EPISODES, "room"):
        journal[state["scene"]] = state.get("dialogue", [])[-20:]
    notes = [
        state.get(key, {}).get("Катер")
        for key in ("meeting_memory", "box_memory", "broken_box_memory", "room_memory", "notes")
    ]
    return {"shared_events": journal, "own_impressions": list(dict.fromkeys(note for note in notes if note)),
            "relationship_observations": impressions(state, "Катер")}
