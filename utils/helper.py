from datetime import datetime


def make_dict_json_serializable(d: dict):
    """
    Recursively finds and converts datetime objects within a dictionary 
    to ISO 8601 formatted strings, making it safe for JSON serialization.
    """
    for k, v in d.items():
        if isinstance(v, dict):
            make_dict_json_serializable(v)
        elif isinstance(v, list):
            # Iterate through list items
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    make_dict_json_serializable(item)
                elif isinstance(item, datetime):
                    v[i] = item.isoformat()
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d