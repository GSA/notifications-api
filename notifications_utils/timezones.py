import os

import pytz
from dateutil import parser

local_timezone = pytz.timezone(os.getenv("TIMEZONE", "America/New_York"))


def utc_string_to_aware_gmt_datetime(date):
    """
    Date can either be a string, naïve UTC datetime or an aware UTC datetime
    Returns an aware local datetime, essentially the time you'd see on your clock
    """
    date = parser.parse(date)
    forced_utc = date.replace(tzinfo=pytz.utc)
    return forced_utc.astimezone(local_timezone)
