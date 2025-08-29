from sqlalchemy import delete, select, update
from sqlalchemy.sql.expression import func

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.enums import UserState
from app.models import Domain, Organization, Service, User


def dao_get_organizations():
    stmt = select(Organization).order_by(
        Organization.active.desc(), Organization.name.asc()
    )
    return db.session.execute(stmt).scalars().all()


def dao_count_organizations_with_live_services():
    stmt = (
        select(func.count(func.distinct(Organization.id)))
        .join(Organization.services)
        .where(
            Service.active.is_(True),
            Service.restricted.is_(False),
            Service.count_as_live.is_(True),
        )
    )
    return db.session.execute(stmt).scalar() or 0


def dao_get_organization_services(organization_id):
    stmt = select(Organization).where(Organization.id == organization_id)
    return db.session.execute(stmt).scalars().one().services


def dao_get_organization_live_services(organization_id):
    stmt = select(Service).where(
        Service.organization_id == organization_id, Service.restricted == False  # noqa
    )
    return db.session.execute(stmt).scalars().all()


def dao_get_organization_by_id(organization_id):
    stmt = select(Organization).where(Organization.id == organization_id)
    return db.session.execute(stmt).scalars().one()


def dao_get_organization_by_email_address(email_address):
    email_address = email_address.lower().replace(".gsi.gov.uk", ".gov.uk")
    stmt = select(Domain).order_by(func.char_length(Domain.domain).desc())
    domains = db.session.execute(stmt).scalars().all()
    for domain in domains:
        if email_address.endswith(
            "@{}".format(domain.domain)
        ) or email_address.endswith(".{}".format(domain.domain)):
            stmt = select(Organization).where(Organization.id == domain.organization_id)
            return db.session.execute(stmt).scalars().one()

    return None


def dao_get_organization_by_service_id(service_id):
    stmt = (
        select(Organization).join(Organization.services).where(Service.id == service_id)
    )
    return db.session.execute(stmt).scalars().first()


@autocommit
def dao_create_organization(organization):
    db.session.add(organization)


@autocommit
def dao_update_organization(organization_id, **kwargs):
    domains = kwargs.pop("domains", None)
    stmt = (
        update(Organization).where(Organization.id == organization_id).values(**kwargs)
    )
    num_updated = db.session.execute(stmt).rowcount

    if isinstance(domains, list):
        stmt = delete(Domain).where(Domain.organization_id == organization_id)
        db.session.execute(stmt)
        db.session.bulk_save_objects(
            [
                Domain(domain=domain.lower(), organization_id=organization_id)
                for domain in domains
            ]
        )

    organization = db.session.get(Organization, organization_id)
    if "organization_type" in kwargs:
        _update_organization_services(
            organization, "organization_type", only_where_none=False
        )

    if "email_branding_id" in kwargs:
        _update_organization_services(organization, "email_branding")

    return num_updated


@version_class(
    VersionOptions(Service, must_write_history=False),
)
def _update_organization_services(organization, attribute, only_where_none=True):
    for service in organization.services:
        if getattr(service, attribute) is None or not only_where_none:
            setattr(service, attribute, getattr(organization, attribute))
        db.session.add(service)


@autocommit
@version_class(Service)
def dao_add_service_to_organization(service, organization_id):
    stmt = select(Organization).where(Organization.id == organization_id)
    organization = db.session.execute(stmt).scalars().one()

    service.organization_id = organization_id
    service.organization_type = organization.organization_type

    db.session.add(service)


def dao_get_users_for_organization(organization_id):
    return (
        db.session.query(User)
        .join(User.organizations)
        .where(Organization.id == organization_id, User.state == UserState.ACTIVE)
        .order_by(User.created_at)
        .all()
    )


@autocommit
def dao_add_user_to_organization(organization_id, user_id):
    organization = dao_get_organization_by_id(organization_id)
    stmt = select(User).where(User.id == user_id)
    user = db.session.execute(stmt).scalars().one()
    user.organizations.append(organization)
    db.session.add(organization)
    return user


@autocommit
def dao_remove_user_from_organization(organization, user):
    organization.users.remove(user)
