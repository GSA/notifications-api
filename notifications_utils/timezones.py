import os
from zoneinfo import ZoneInfo

from dateutil import parser

local_timezone = os.getenv("TIMEZONE", ZoneInfo("America/New_York"))


def utc_string_to_aware_gmt_datetime(date):
    """
    Date can either be a string, naïve UTC datetime or an aware UTC datetime
    Returns an aware local datetime, essentially the time you'd see on your clock
    """
    date = parser.parse(date)
    forced_utc = date.replace(tzinfo=ZoneInfo.UTC)
    return forced_utc.astimezone(local_timezone)
