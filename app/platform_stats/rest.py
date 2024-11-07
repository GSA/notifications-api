from datetime import datetime

from flask import Blueprint, jsonify, request

from app.dao.date_util import get_calendar_year_for_datetime
from app.dao.fact_billing_dao import (
    fetch_billing_details_for_all_services,
    fetch_daily_sms_provider_volumes_for_platform,
    fetch_daily_volumes_for_platform,
    fetch_sms_billing_for_all_services,
    fetch_volumes_by_service,
)
from app.dao.fact_notification_status_dao import (
    fetch_notification_status_totals_for_all_services,
)
from app.errors import InvalidRequest, register_errors
from app.platform_stats.platform_stats_schema import platform_stats_request
from app.schema_validation import validate
from app.service.statistics import format_admin_stats
from app.utils import get_midnight_in_utc, utc_now

platform_stats_blueprint = Blueprint("platform_stats", __name__)

register_errors(platform_stats_blueprint)


@platform_stats_blueprint.route("")
def get_platform_stats():
    if request.args:
        validate(request.args, platform_stats_request)

    # If start and end date are not set, we are expecting today's stats.
    today = str(utc_now().date())

    start_date = datetime.strptime(
        request.args.get("start_date", today), "%Y-%m-%d"
    ).date()
    end_date = datetime.strptime(request.args.get("end_date", today), "%Y-%m-%d").date()
    data = fetch_notification_status_totals_for_all_services(
        start_date=start_date, end_date=end_date
    )
    stats = format_admin_stats(data)

    return jsonify(stats)


def validate_date_format(date_to_validate):
    try:
        validated_date = datetime.strptime(date_to_validate, "%Y-%m-%d").date()
    except ValueError:
        raise InvalidRequest(
            message="Input must be a date in the format: YYYY-MM-DD", status_code=400
        )
    return validated_date


def validate_date_range_is_within_a_financial_year(start_date, end_date):
    start_date = validate_date_format(start_date)
    end_date = validate_date_format(end_date)
    if end_date < start_date:
        raise InvalidRequest(
            message="Start date must be before end date", status_code=400
        )

    start_fy = get_calendar_year_for_datetime(get_midnight_in_utc(start_date))
    end_fy = get_calendar_year_for_datetime(get_midnight_in_utc(end_date))

    if start_fy != end_fy:
        raise InvalidRequest(
            message="Date must be in a single financial year.", status_code=400
        )

    return start_date, end_date


@platform_stats_blueprint.route("usage-for-all-services")
@platform_stats_blueprint.route("data-for-billing-report")
def get_data_for_billing_report():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start_date, end_date = validate_date_range_is_within_a_financial_year(
        start_date, end_date
    )

    volumes_by_service = fetch_volumes_by_service(start_date, end_date).all()

    combined = {}
    for s in sms_costs:
        if float(s.sms_cost) > 0:
            entry = {
                "organization_id": str(s.organization_id) if s.organization_id else "",
                "organization_name": s.organization_name or "",
                "service_id": str(s.service_id),
                "service_name": s.service_name,
                "sms_cost": float(s.sms_cost),
                "sms_chargeable_units": s.chargeable_billable_sms,
            }
            combined[s.service_id] = entry

    billing_details = fetch_billing_details_for_all_services()
    for service in billing_details:
        if service.service_id in combined:
            combined[service.service_id].update(
                {
                    "purchase_order_number": service.purchase_order_number,
                    "contact_names": service.billing_contact_names,
                    "contact_email_addresses": service.billing_contact_email_addresses,
                    "billing_reference": service.billing_reference,
                }
            )

    # sorting first by name == '' means that blank orgs will be sorted last.

    result = sorted(
        combined.values(),
        key=lambda x: (
            x["organization_name"] == "",
            x["organization_name"],
            x["service_name"],
        ),
    )
    return jsonify(result)


@platform_stats_blueprint.route("daily-volumes-report")
def daily_volumes_report():
    start_date = validate_date_format(request.args.get("start_date"))
    end_date = validate_date_format(request.args.get("end_date"))

    daily_volumes = fetch_daily_volumes_for_platform(start_date, end_date)
    report = []

    for row in daily_volumes:
        report.append(
            {
                "day": row.local_date,
                "sms_totals": int(row.sms_totals),
                "sms_fragment_totals": int(row.sms_fragment_totals),
                "sms_chargeable_units": int(row.sms_chargeable_units),
                "email_totals": int(row.email_totals),
            }
        )
    return jsonify(report)


@platform_stats_blueprint.route("daily-sms-provider-volumes-report")
def daily_sms_provider_volumes_report():
    start_date = validate_date_format(request.args.get("start_date"))
    end_date = validate_date_format(request.args.get("end_date"))

    daily_volumes = fetch_daily_sms_provider_volumes_for_platform(start_date, end_date)
    report = []

    for row in daily_volumes:
        report.append(
            {
                "day": row.local_date.isoformat(),
                "provider": row.provider,
                "sms_totals": int(row.sms_totals),
                "sms_fragment_totals": int(row.sms_fragment_totals),
                "sms_chargeable_units": int(row.sms_chargeable_units),
                # convert from Decimal to float as it's not json serialisable
                "sms_cost": float(row.sms_cost),
            }
        )
    return jsonify(report)


@platform_stats_blueprint.route("volumes-by-service")
def volumes_by_service_report():
    start_date = validate_date_format(request.args.get("start_date"))
    end_date = validate_date_format(request.args.get("end_date"))

    volumes_by_service = fetch_volumes_by_service(start_date, end_date)
    report = []

    for row in volumes_by_service:
        report.append(
            {
                "service_name": row.service_name,
                "service_id": str(row.service_id),
                "organization_name": (
                    row.organization_name if row.organization_name else ""
                ),
                "organization_id": (
                    str(row.organization_id) if row.organization_id else ""
                ),
                "free_allowance": int(row.free_allowance),
                "sms_notifications": int(row.sms_notifications),
                "sms_chargeable_units": int(row.sms_chargeable_units),
                "email_totals": int(row.email_totals),
            }
        )

    return jsonify(report)
