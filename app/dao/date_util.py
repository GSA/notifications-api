import calendar
from datetime import date, datetime, time, timedelta

from app.utils import utc_now


def get_months_for_financial_year(year):
    return [
        month for month in (get_months_for_year(1, 13, year)) if month < datetime.now()
    ]


def get_months_for_year(start, end, year):
    return [datetime(year, month, 1) for month in range(start, end)]


def get_calendar_year(year):
    return get_new_years(year), get_new_years(year + 1) - timedelta(microseconds=1)


def get_calendar_year_dates(year):
    year_start_datetime, year_end_datetime = get_calendar_year(year)

    return (year_start_datetime.date(), year_end_datetime.date())


def get_current_calendar_year():
    now = utc_now()
    current_year = int(now.strftime("%Y"))
    year = current_year
    return get_calendar_year(year)


def get_new_years(year):
    return datetime(year, 1, 1, 0, 0, 0)


def get_month_start_and_end_date_in_utc(month_year):
    """
    This function return the start and date of the month_year as UTC,
    :param month_year: the datetime to calculate the start and end date for that month
    :return: start_date, end_date, month
    """
    import calendar

    _, num_days = calendar.monthrange(month_year.year, month_year.month)
    first_day = datetime(month_year.year, month_year.month, 1, 0, 0, 0)
    last_day = datetime(month_year.year, month_year.month, num_days, 23, 59, 59, 99999)
    return first_day, last_day


def get_current_calendar_year_start_year():
    now = datetime.now()
    financial_year_start = now.year
    start_date, end_date = get_calendar_year(now.year)
    if now < start_date:
        financial_year_start = financial_year_start - 1
    return financial_year_start


def get_calendar_year_for_datetime(start_date):
    if isinstance(start_date, date):
        start_date = datetime.combine(start_date, time.min)

    year = int(start_date.strftime("%Y"))
    if start_date < get_new_years(year):
        return year - 1
    else:
        return year


def get_number_of_days_for_month(year, month):
    return calendar.monthrange(year, month)[1]


def generate_date_range(start_date, end_date=None, days=0):
    if end_date:
        current_date = start_date
        while current_date <= end_date:
            try:
                yield current_date.date()
            except ValueError:
                pass
            current_date += timedelta(days=1)
    elif days > 0:
        end_date = start_date + timedelta(days=days)
        current_date = start_date
        while current_date < end_date:
            try:
                yield current_date.date()
            except ValueError:
                pass
            current_date += timedelta(days=1)
    else:
        return "An end_date or number of days must be specified"


def generate_hourly_range(start_date, end_date=None, hours=0):
    if end_date:
        current_time = start_date
        while current_time <= end_date:
            try:
                yield current_time
            except ValueError:
                pass
            current_time += timedelta(hours=1)
    elif hours > 0:
        end_time = start_date + timedelta(hours=hours)
        current_time = start_date
        while current_time < end_time:
            try:
                yield current_time
            except ValueError:
                pass
            current_time += timedelta(hours=1)
    else:
        return "An end_date or number of hours must be specified"
