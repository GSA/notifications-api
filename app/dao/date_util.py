from datetime import date, datetime, time, timedelta


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
    now = datetime.utcnow()
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
