import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.dao.organization_dao import (
    dao_add_service_to_organization,
    dao_add_user_to_organization,
    dao_get_organization_by_email_address,
    dao_get_organization_by_id,
    dao_get_organization_by_service_id,
    dao_get_organization_services,
    dao_get_organizations,
    dao_get_users_for_organization,
    dao_update_organization,
)
from app.enums import OrganizationType, UserState
from app.models import Organization, Service
from app.utils import utc_now
from tests.app.db import (
    create_domain,
    create_email_branding,
    create_organization,
    create_service,
    create_user,
)


def test_get_organizations_gets_all_organizations_alphabetically_with_active_organizations_first(
    notify_db_session,
):
    m_active_org = create_organization(name="m_active_organization")
    z_inactive_org = create_organization(name="z_inactive_organization", active=False)
    a_inactive_org = create_organization(name="a_inactive_organization", active=False)
    z_active_org = create_organization(name="z_active_organization")
    a_active_org = create_organization(name="a_active_organization")

    organizations = dao_get_organizations()

    assert len(organizations) == 5
    assert organizations[0] == a_active_org
    assert organizations[1] == m_active_org
    assert organizations[2] == z_active_org
    assert organizations[3] == a_inactive_org
    assert organizations[4] == z_inactive_org


def test_get_organization_by_id_gets_correct_organization(notify_db_session):
    organization = create_organization()

    organization_from_db = dao_get_organization_by_id(organization.id)

    assert organization_from_db == organization


def test_update_organization(notify_db_session):
    create_organization()

    stmt = select(Organization)
    organization = db.session.execute(stmt).scalars().one()
    user = create_user()
    email_branding = create_email_branding()

    data = {
        "name": "new name",
        "organization_type": OrganizationType.STATE,
        "agreement_signed": True,
        "agreement_signed_at": utc_now(),
        "agreement_signed_by_id": user.id,
        "agreement_signed_version": 999.99,
        "email_branding_id": email_branding.id,
    }

    for attribute, value in data.items():
        assert getattr(organization, attribute) != value

    assert organization.updated_at is None

    dao_update_organization(organization.id, **data)

    stmt = select(Organization)
    organization = db.session.execute(stmt).scalars().one()

    for attribute, value in data.items():
        assert getattr(organization, attribute) == value

    assert organization.updated_at


@pytest.mark.parametrize(
    "domain_list, expected_domains",
    (
        (["abc", "def"], {"abc", "def"}),
        (["ABC", "DEF"], {"abc", "def"}),
        ([], set()),
        (None, {"123", "456"}),
    ),
)
def test_update_organization_domains_lowercases(
    notify_db_session,
    domain_list,
    expected_domains,
):
    create_organization()

    stmt = select(Organization)
    organization = db.session.execute(stmt).scalars().one()

    # Seed some domains
    dao_update_organization(organization.id, domains=["123", "456"])

    # This should overwrite the seeded domains
    dao_update_organization(organization.id, domains=domain_list)

    assert {domain.domain for domain in organization.domains} == expected_domains


@pytest.mark.parametrize("domain_list, expected_domains", ((["abc", "ABC"], {"abc"}),))
def test_update_organization_domains_lowercases_integrity_error(
    notify_db_session,
    domain_list,
    expected_domains,
):
    create_organization()

    stmt = select(Organization)
    organization = db.session.execute(stmt).scalars().one()

    # Seed some domains
    dao_update_organization(organization.id, domains=["123", "456"])

    with pytest.raises(expected_exception=IntegrityError):
        # This should overwrite the seeded domains
        dao_update_organization(organization.id, domains=domain_list)

        assert {domain.domain for domain in organization.domains} == expected_domains


def test_update_organization_does_not_update_the_service_if_certain_attributes_not_provided(
    sample_service,
    sample_organization,
):
    email_branding = create_email_branding()

    sample_service.organization_type = OrganizationType.STATE
    sample_organization.organization_type = OrganizationType.FEDERAL
    sample_organization.email_branding = email_branding

    sample_organization.services.append(sample_service)
    db.session.commit()

    assert sample_organization.name == "sample organization"

    dao_update_organization(sample_organization.id, name="updated org name")

    assert sample_organization.name == "updated org name"

    assert sample_organization.organization_type == OrganizationType.FEDERAL
    assert sample_service.organization_type == OrganizationType.STATE

    assert sample_organization.email_branding == email_branding
    assert sample_service.email_branding is None


def test_update_organization_updates_the_service_org_type_if_org_type_is_provided(
    sample_service,
    sample_organization,
):
    sample_service.organization_type = OrganizationType.STATE
    sample_organization.organization_type = OrganizationType.STATE

    sample_organization.services.append(sample_service)
    db.session.commit()

    dao_update_organization(
        sample_organization.id, organization_type=OrganizationType.FEDERAL
    )

    assert sample_organization.organization_type == OrganizationType.FEDERAL
    assert sample_service.organization_type == OrganizationType.FEDERAL
    stmt = select(Service.get_history_model()).where(
        Service.get_history_model().id == sample_service.id,
        Service.get_history_model().version == 2,
    )
    assert (
        db.session.execute(stmt).scalars().one().organization_type
        == OrganizationType.FEDERAL
    )


def test_update_organization_updates_the_service_branding_if_branding_is_provided(
    sample_service,
    sample_organization,
):
    email_branding = create_email_branding()

    sample_organization.services.append(sample_service)
    db.session.commit()

    dao_update_organization(sample_organization.id, email_branding_id=email_branding.id)

    assert sample_organization.email_branding == email_branding
    assert sample_service.email_branding == email_branding


def test_update_organization_does_not_override_service_branding(
    sample_service,
    sample_organization,
):
    email_branding = create_email_branding()
    custom_email_branding = create_email_branding(name="custom")

    sample_service.email_branding = custom_email_branding

    sample_organization.services.append(sample_service)
    db.session.commit()

    dao_update_organization(sample_organization.id, email_branding_id=email_branding.id)

    assert sample_organization.email_branding == email_branding
    assert sample_service.email_branding == custom_email_branding


def test_add_service_to_organization(sample_service, sample_organization):
    assert sample_organization.services == []

    sample_service.organization_type = OrganizationType.FEDERAL
    sample_organization.organization_type = OrganizationType.STATE

    dao_add_service_to_organization(sample_service, sample_organization.id)

    assert len(sample_organization.services) == 1
    assert sample_organization.services[0].id == sample_service.id

    assert sample_service.organization_type == sample_organization.organization_type
    stmt = select(Service.get_history_model()).where(
        Service.get_history_model().id == sample_service.id,
        Service.get_history_model().version == 2,
    )
    assert (
        db.session.execute(stmt).scalars().one().organization_type
        == sample_organization.organization_type
    )
    assert sample_service.organization_id == sample_organization.id


def test_get_organization_services(sample_service, sample_organization):
    another_service = create_service(service_name="service 2")
    another_org = create_organization()

    dao_add_service_to_organization(sample_service, sample_organization.id)
    dao_add_service_to_organization(another_service, sample_organization.id)

    org_services = dao_get_organization_services(sample_organization.id)
    other_org_services = dao_get_organization_services(another_org.id)

    assert [sample_service.name, another_service.name] == sorted(
        [s.name for s in org_services]
    )
    assert not other_org_services


def test_get_organization_by_service_id(sample_service, sample_organization):
    another_service = create_service(service_name="service 2")
    another_org = create_organization()

    dao_add_service_to_organization(sample_service, sample_organization.id)
    dao_add_service_to_organization(another_service, another_org.id)

    organization_1 = dao_get_organization_by_service_id(sample_service.id)
    organization_2 = dao_get_organization_by_service_id(another_service.id)

    assert organization_1 == sample_organization
    assert organization_2 == another_org


def test_dao_get_users_for_organization(sample_organization):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")

    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=first.id
    )
    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=second.id
    )

    results = dao_get_users_for_organization(organization_id=sample_organization.id)

    assert len(results) == 2
    assert results[0] == first
    assert results[1] == second


def test_dao_get_users_for_organization_returns_empty_list(sample_organization):
    results = dao_get_users_for_organization(organization_id=sample_organization.id)
    assert len(results) == 0


def test_dao_get_users_for_organization_only_returns_active_users(sample_organization):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")

    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=first.id
    )
    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=second.id
    )

    second.state = UserState.INACTIVE

    results = dao_get_users_for_organization(organization_id=sample_organization.id)
    assert len(results) == 1
    assert results[0] == first


def test_add_user_to_organization_returns_user(sample_organization):
    org_user = create_user()
    assert not org_user.organizations

    added_user = dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=org_user.id
    )
    assert len(added_user.organizations) == 1
    assert added_user.organizations[0] == sample_organization


def test_add_user_to_organization_when_user_does_not_exist(sample_organization):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_add_user_to_organization(
            organization_id=sample_organization.id, user_id=uuid.uuid4()
        )


def test_add_user_to_organization_when_organization_does_not_exist(sample_user):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_add_user_to_organization(
            organization_id=uuid.uuid4(), user_id=sample_user.id
        )


@pytest.mark.parametrize(
    "domain, expected_org",
    (
        ("unknown.gov.uk", False),
        ("example.gov.uk", True),
    ),
)
def test_get_organization_by_email_address(domain, expected_org, notify_db_session):
    org = create_organization()
    create_domain("example.gov.uk", org.id)
    create_domain("test.gov.uk", org.id)

    another_org = create_organization(name="Another")
    create_domain("cabinet-office.gov.uk", another_org.id)
    create_domain("cabinetoffice.gov.uk", another_org.id)

    found_org = dao_get_organization_by_email_address("test@{}".format(domain))

    if expected_org:
        assert found_org is org
    else:
        assert found_org is None


def test_get_organization_by_email_address_ignores_gsi_gov_uk(notify_db_session):
    org = create_organization()
    create_domain("example.gov.uk", org.id)

    found_org = dao_get_organization_by_email_address(
        "test_gsi_address@example.gsi.gov.uk"
    )
    assert org == found_org
