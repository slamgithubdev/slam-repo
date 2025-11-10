from datetime import datetime


def replace_prefix_with_timestamp(field: str, dt: datetime = None) -> str:
    """
    Removes the first 10 characters of a field and replaces them with YYMMDDHHMM timestamp.

    Args:
        field: The input string (e.g., externalPersonId)
        dt: Optional datetime object. If None, uses current datetime.

    Returns:
        String with first 10 chars replaced by timestamp
    """
    if dt is None:
        dt = datetime.now()

    # Format datetime as YYMMDDHHMM
    timestamp = dt.strftime("%y%m%d%H%M")

    # Remove first 10 chars and prepend timestamp
    return timestamp + field[10:]
