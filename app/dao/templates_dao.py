import uuid

from sqlalchemy import asc, desc, select

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.models import Template, TemplateHistory, TemplateRedacted
from app.utils import utc_now


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_create_template(template):
    template.id = (
        uuid.uuid4()
    )  # must be set now so version history model can use same id
    template.archived = False

    redacted_dict = {
        "template": template,
        "redact_personalisation": False,
    }
    if template.created_by:
        redacted_dict.update({"updated_by": template.created_by})
    else:
        redacted_dict.update({"updated_by_id": template.created_by_id})

    template.template_redacted = TemplateRedacted(**redacted_dict)

    db.session.add(template)


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_update_template(template):
    db.session.add(template)


@autocommit
def dao_redact_template(template, user_id):
    template.template_redacted.redact_personalisation = True
    template.template_redacted.updated_at = utc_now()
    template.template_redacted.updated_by_id = user_id
    db.session.add(template.template_redacted)


def dao_get_template_by_id_and_service_id(template_id, service_id, version=None):
    if version is not None:
        stmt = select(TemplateHistory).where(
            TemplateHistory.id == template_id,
            TemplateHistory.hidden == False,  # noqa
            TemplateHistory.service_id == service_id,
            TemplateHistory.version == version,
        )
        return db.session.execute(stmt).scalars().one()
    stmt = select(Template).where(
        Template.id == template_id,
        Template.hidden == False,  # noqa
        Template.service_id == service_id,
    )
    return db.session.execute(stmt).scalars().one()


def dao_get_template_by_id(template_id, version=None):
    if version is not None:
        stmt = select(TemplateHistory).where(
            TemplateHistory.id == template_id, TemplateHistory.version == version
        )
        return db.session.execute(stmt).scalars().one()
    stmt = select(Template).where(Template.id == template_id)
    return db.session.execute(stmt).scalars().one()


def dao_get_all_templates_for_service(service_id, template_type=None):
    if template_type is not None:
        stmt = (
            select(Template)
            .where(
                Template.service_id == service_id,
                Template.template_type == template_type,
                Template.hidden == False,  # noqa
                Template.archived == False,  # noqa
            )
            .order_by(
                asc(Template.name),
                asc(Template.template_type),
            )
        )
        return db.session.execute(stmt).scalars().all()
    stmt = (
        select(Template)
        .where(
            Template.service_id == service_id,
            Template.hidden == False,  # noqa
            Template.archived == False,  # noqa
        )
        .order_by(
            asc(Template.name),
            asc(Template.template_type),
        )
    )
    return db.session.execute(stmt).scalars().all()


def dao_get_template_versions(service_id, template_id):
    stmt = (
        select(TemplateHistory)
        .where(
            TemplateHistory.service_id == service_id,
            TemplateHistory.id == template_id,
            TemplateHistory.hidden == False,  # noqa
        )
        .order_by(desc(TemplateHistory.version))
    )
    return db.session.execute(stmt).scalars().all()
