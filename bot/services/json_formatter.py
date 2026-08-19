import json


def format_json(raw_json: str) -> str:
    data = json.loads(raw_json)
    return json.dumps(data, ensure_ascii=False, indent=4)
