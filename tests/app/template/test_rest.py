import json
import random
import string
import uuid
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select

from app import db
from app.dao.templates_dao import dao_get_template_by_id, dao_redact_template
from app.enums import ServicePermissionType, TemplateProcessType, TemplateType
from app.models import Template, TemplateHistory
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from tests import create_admin_authorization_header
from tests.app.db import create_service, create_template, create_template_folder


@pytest.mark.parametrize(
    "template_type, subject",
    [
        (TemplateType.SMS, None),
        (TemplateType.EMAIL, "subject"),
    ],
)
def test_should_create_a_new_template_for_a_service(
    client, sample_user, template_type, subject
):
    service = create_service(service_permissions=[template_type])
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template <b>content</b>",
        "service": str(service.id),
        "created_by": str(sample_user.id),
    }
    if subject:
        data.update({"subject": subject})
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"]["name"] == "my template"
    assert json_resp["data"]["template_type"] == template_type
    assert json_resp["data"]["content"] == "template <b>content</b>"
    assert json_resp["data"]["service"] == str(service.id)
    assert json_resp["data"]["id"]
    assert json_resp["data"]["version"] == 1
    assert json_resp["data"]["process_type"] == TemplateProcessType.NORMAL
    assert json_resp["data"]["created_by"] == str(sample_user.id)
    if subject:
        assert json_resp["data"]["subject"] == "subject"
    else:
        assert not json_resp["data"]["subject"]

    template = db.session.get(Template, json_resp["data"]["id"])
    from app.schemas import template_schema

    assert sorted(json_resp["data"]) == sorted(template_schema.dump(template))


def test_create_a_new_template_for_a_service_adds_folder_relationship(
    client, sample_service
):
    parent_folder = create_template_folder(service=sample_service, name="parent folder")

    data = {
        "name": "my template",
        "template_type": TemplateType.SMS,
        "content": "template <b>content</b>",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
        "parent_folder_id": str(parent_folder.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{sample_service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    stmt = select(Template).where(Template.name == "my template")
    template = db.session.execute(stmt).scalars().first()
    assert template.folder == parent_folder


def test_create_template_should_return_400_if_folder_is_for_a_different_service(
    client, sample_service
):
    service2 = create_service(service_name="second service")
    parent_folder = create_template_folder(service=service2)

    data = {
        "name": "my template",
        "template_type": TemplateType.SMS,
        "content": "template <b>content</b>",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
        "parent_folder_id": str(parent_folder.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{sample_service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    assert (
        json.loads(response.get_data(as_text=True))["message"]
        == "parent_folder_id not found"
    )


def test_create_template_should_return_400_if_folder_does_not_exist(
    client, sample_service
):
    data = {
        "name": "my template",
        "template_type": TemplateType.SMS,
        "content": "template <b>content</b>",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
        "parent_folder_id": str(uuid.uuid4()),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{sample_service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    assert (
        json.loads(response.get_data(as_text=True))["message"]
        == "parent_folder_id not found"
    )


def test_should_raise_error_if_service_does_not_exist_on_create(
    client, sample_user, fake_uuid
):
    data = {
        "name": "my template",
        "template_type": TemplateType.SMS,
        "content": "template content",
        "service": fake_uuid,
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{fake_uuid}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


@pytest.mark.parametrize(
    "permissions, template_type, subject, expected_error",
    [
        (
            [ServicePermissionType.EMAIL],
            TemplateType.SMS,
            None,
            {"template_type": ["Creating text message templates is not allowed"]},
        ),
        (
            [ServicePermissionType.SMS],
            TemplateType.EMAIL,
            "subject",
            {"template_type": ["Creating email templates is not allowed"]},
        ),
    ],
)
def test_should_raise_error_on_create_if_no_permission(
    client, sample_user, permissions, template_type, subject, expected_error
):
    service = create_service(service_permissions=permissions)
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template content",
        "service": str(service.id),
        "created_by": str(sample_user.id),
    }
    if subject:
        data.update({"subject": subject})

    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 403
    assert json_resp["result"] == "error"
    assert json_resp["message"] == expected_error


@pytest.mark.parametrize(
    "template_type, permissions, expected_error",
    [
        (
            TemplateType.SMS,
            [ServicePermissionType.EMAIL],
            {"template_type": ["Updating text message templates is not allowed"]},
        ),
        (
            TemplateType.EMAIL,
            [ServicePermissionType.SMS],
            {"template_type": ["Updating email templates is not allowed"]},
        ),
    ],
)
def test_should_be_error_on_update_if_no_permission(
    client,
    sample_user,
    notify_db_session,
    template_type,
    permissions,
    expected_error,
):
    service = create_service(service_permissions=permissions)
    template_without_permission = create_template(service, template_type=template_type)
    data = {"content": "new template content", "created_by": str(sample_user.id)}

    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    update_response = client.post(
        f"/service/{template_without_permission.service_id}/template/{template_without_permission.id}",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )

    json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_response.status_code == 403
    assert json_resp["result"] == "error"
    assert json_resp["message"] == expected_error


def test_should_error_if_created_by_missing(client, sample_user, sample_service):
    service_id = str(sample_service.id)
    data = {
        "name": "my template",
        "template_type": TemplateType.SMS,
        "content": "template content",
        "service": service_id,
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{service_id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["errors"][0]["error"] == "ValidationError"
    assert json_resp["errors"][0]["message"] == "created_by is a required property"


def test_should_be_error_if_service_does_not_exist_on_update(client, fake_uuid):
    data = {"name": "my template"}
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{fake_uuid}/template/{fake_uuid}",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


@st.composite
def maybe_invalid_uuid(draw):
    if draw(st.booleans()):
        return str(draw(st.uuids()))
    else:
        return draw(st.text(min_size=1, max_size=36))


@given(
    fuzzed_service_id=maybe_invalid_uuid(),
    fuzzed_template_id=maybe_invalid_uuid(),
    fuzzed_template_name=st.text(min_size=1, max_size=100),
)
def test_fuzz_should_be_error_if_service_does_not_exist_on_update(
    client, fuzzed_service_id, fuzzed_template_id, fuzzed_template_name
):
    """
    Hypothesis-based fuzz test to ensure that when updating a template
    for a non-existent service, the API returns a 404 with the correct error message
    """
    data = {"name": fuzzed_template_name}
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    response = client.post(
        f"/service/{fuzzed_service_id}/template/{fuzzed_template_id}",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))

    assert response.status_code == 404
    assert json_resp["result"] == "error"


@pytest.mark.parametrize("template_type", [TemplateType.EMAIL])
def test_must_have_a_subject_on_an_email_template(
    client, sample_user, sample_service, template_type
):
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["errors"][0]["error"] == "ValidationError"
    assert json_resp["errors"][0]["message"] == "subject is a required property"


def test_update_should_update_a_template(client, sample_user):
    service = create_service()
    template = create_template(service, template_type=TemplateType.SMS)

    assert template.created_by == service.created_by
    assert template.created_by != sample_user

    data = {
        "content": "my template has new content, swell!",
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    update_response = client.post(
        f"/service/{service.id}/template/{template.id}",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )

    assert update_response.status_code == 200
    update_json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_json_resp["data"]["content"] == (
        "my template has new content, swell!"
    )
    assert update_json_resp["data"]["name"] == template.name
    assert update_json_resp["data"]["template_type"] == template.template_type
    assert update_json_resp["data"]["version"] == 2

    assert update_json_resp["data"]["created_by"] == str(sample_user.id)
    template_created_by_users = [
        template.created_by_id
        for template in db.session.execute(select(TemplateHistory)).scalars().all()
    ]
    assert len(template_created_by_users) == 2
    assert service.created_by.id in template_created_by_users
    assert sample_user.id in template_created_by_users


def test_should_be_able_to_archive_template(client, sample_template):
    data = {
        "name": sample_template.name,
        "template_type": sample_template.template_type,
        "content": sample_template.content,
        "archived": True,
        "service": str(sample_template.service.id),
        "created_by": str(sample_template.created_by.id),
    }

    json_data = json.dumps(data)

    auth_header = create_admin_authorization_header()

    resp = client.post(
        f"/service/{sample_template.service.id}/template/{sample_template.id}",
        headers=[("Content-Type", "application/json"), auth_header],
        data=json_data,
    )

    assert resp.status_code == 200
    assert db.session.execute(select(Template)).scalars().first().archived


def test_should_be_able_to_archive_template_should_remove_template_folders(
    client, sample_service
):
    template_folder = create_template_folder(service=sample_service)
    template = create_template(service=sample_service, folder=template_folder)

    data = {
        "archived": True,
    }

    client.post(
        f"/service/{sample_service.id}/template/{template.id}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )

    updated_template = db.session.get(Template, template.id)
    assert updated_template.archived
    assert not updated_template.folder


def test_should_be_able_to_get_all_templates_for_a_service(
    client, sample_user, sample_service
):
    data = {
        "name": "my template 1",
        "template_type": TemplateType.EMAIL,
        "subject": "subject 1",
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data_1 = json.dumps(data)
    data = {
        "name": "my template 2",
        "template_type": TemplateType.EMAIL,
        "subject": "subject 2",
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data_2 = json.dumps(data)
    auth_header = create_admin_authorization_header()
    client.post(
        f"/service/{sample_service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data_1,
    )
    auth_header = create_admin_authorization_header()

    client.post(
        f"/service/{sample_service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data_2,
    )

    auth_header = create_admin_authorization_header()

    response = client.get(
        f"/service/{sample_service.id}/template", headers=[auth_header]
    )

    assert response.status_code == 200
    update_json_resp = json.loads(response.get_data(as_text=True))
    assert update_json_resp["data"][0]["name"] == "my template 1"
    assert update_json_resp["data"][0]["version"] == 1
    assert update_json_resp["data"][0]["created_at"]
    assert update_json_resp["data"][1]["name"] == "my template 2"
    assert update_json_resp["data"][1]["version"] == 1
    assert update_json_resp["data"][1]["created_at"]


def test_should_get_only_templates_for_that_service(admin_request, notify_db_session):
    service_1 = create_service(service_name="service_1")
    service_2 = create_service(service_name="service_2")
    id_1 = create_template(service_1).id
    id_2 = create_template(service_1).id
    id_3 = create_template(service_2).id

    json_resp_1 = admin_request.get(
        "template.get_all_templates_for_service",
        service_id=service_1.id,
    )
    json_resp_2 = admin_request.get(
        "template.get_all_templates_for_service",
        service_id=service_2.id,
    )

    assert {template["id"] for template in json_resp_1["data"]} == {
        str(id_1),
        str(id_2),
    }
    assert {template["id"] for template in json_resp_2["data"]} == {str(id_3)}


@pytest.mark.parametrize(
    "extra_args",
    (
        {},
        {"detailed": True},
        {"detailed": "True"},
    ),
)
def test_should_get_return_all_fields_by_default(
    admin_request,
    sample_email_template,
    extra_args,
):
    json_response = admin_request.get(
        "template.get_all_templates_for_service",
        service_id=sample_email_template.service.id,
        **extra_args,
    )
    assert json_response["data"][0].keys() == {
        "archived",
        "content",
        "created_at",
        "created_by",
        "folder",
        "hidden",
        "id",
        "name",
        "process_type",
        "redact_personalisation",
        "reply_to",
        "reply_to_text",
        "service",
        "subject",
        "template_redacted",
        "template_type",
        "updated_at",
        "version",
    }


@pytest.mark.parametrize(
    "extra_args",
    (
        {"detailed": False},
        {"detailed": "False"},
    ),
)
@pytest.mark.parametrize(
    "template_type, expected_content",
    (
        (TemplateType.EMAIL, None),
        (TemplateType.SMS, None),
    ),
)
def test_should_not_return_content_and_subject_if_requested(
    admin_request,
    sample_service,
    extra_args,
    template_type,
    expected_content,
):
    create_template(
        sample_service,
        template_type=template_type,
        content="This is a test",
    )
    json_response = admin_request.get(
        "template.get_all_templates_for_service",
        service_id=sample_service.id,
        **extra_args,
    )
    assert json_response["data"][0].keys() == {
        "content",
        "folder",
        "id",
        "name",
        "template_type",
    }
    assert json_response["data"][0]["content"] == expected_content


@pytest.mark.parametrize(
    "subject, content, template_type",
    [
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            TemplateType.EMAIL,
        ),
        (None, "hello ((name)) we’ve received your ((thing))", TemplateType.SMS),
    ],
)
def test_should_get_a_single_template(
    client, sample_user, sample_service, subject, content, template_type
):
    template = create_template(
        sample_service, template_type=template_type, subject=subject, content=content
    )

    response = client.get(
        f"/service/{sample_service.id}/template/{template.id}",
        headers=[create_admin_authorization_header()],
    )

    data = json.loads(response.get_data(as_text=True))["data"]

    assert response.status_code == 200
    assert data["content"] == content
    assert data["subject"] == subject
    assert data["process_type"] == TemplateProcessType.NORMAL
    assert not data["redact_personalisation"]


@pytest.mark.parametrize(
    "subject, content, path, expected_subject, expected_content, expected_error",
    [
        (
            "about your thing",
            "hello user we’ve received your thing",
            "/service/{}/template/{}/preview",
            "about your thing",
            "hello user we’ve received your thing",
            None,
        ),
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            "/service/{}/template/{}/preview?name=Amala&thing=document",
            "about your document",
            "hello Amala we’ve received your document",
            None,
        ),
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            "/service/{}/template/{}/preview?eman=Amala&gniht=document",
            None,
            None,
            "Missing personalisation: thing, name",
        ),
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            "/service/{}/template/{}/preview?name=Amala&thing=document&foo=bar",
            "about your document",
            "hello Amala we’ve received your document",
            None,
        ),
    ],
)
def test_should_preview_a_single_template(
    client,
    sample_service,
    subject,
    content,
    path,
    expected_subject,
    expected_content,
    expected_error,
):
    template = create_template(
        sample_service,
        template_type=TemplateType.EMAIL,
        subject=subject,
        content=content,
    )

    response = client.get(
        path.format(sample_service.id, template.id),
        headers=[create_admin_authorization_header()],
    )

    content = json.loads(response.get_data(as_text=True))

    if expected_error:
        assert response.status_code == 400
        assert content["message"]["template"] == [expected_error]
    else:
        assert response.status_code == 200
        assert content["content"] == expected_content
        assert content["subject"] == expected_subject


def test_should_return_empty_array_if_no_templates_for_service(client, sample_service):
    auth_header = create_admin_authorization_header()

    response = client.get(
        f"/service/{sample_service.id}/template", headers=[auth_header]
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp["data"]) == 0


def test_should_return_404_if_no_templates_for_service_with_id(
    client, sample_service, fake_uuid
):
    auth_header = create_admin_authorization_header()

    response = client.get(
        f"/service/{sample_service.id}/template/{fake_uuid}",
        headers=[auth_header],
    )

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


@pytest.mark.parametrize("template_type", (TemplateType.SMS,))
def test_create_400_for_over_limit_content(
    client,
    notify_api,
    sample_user,
    fake_uuid,
    template_type,
):
    sample_service = create_service(service_permissions=[template_type])
    content = "".join(
        random.choice(string.ascii_uppercase + string.digits)
        for _ in range(SMS_CHAR_COUNT_LIMIT + 1)
    )
    data = {
        "name": "too big template",
        "template_type": template_type,
        "content": content,
        "service": str(sample_service.id),
        "created_by": str(sample_service.created_by.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{sample_service.id}/template",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert ("Content has a character count greater than the limit of {}").format(
        SMS_CHAR_COUNT_LIMIT
    ) in json_resp["message"]["content"]


def test_update_400_for_over_limit_content(
    client, notify_api, sample_user, sample_template
):
    json_data = json.dumps(
        {
            "content": "".join(
                random.choice(string.ascii_uppercase + string.digits)
                for _ in range(SMS_CHAR_COUNT_LIMIT + 1)
            ),
            "created_by": str(sample_user.id),
        }
    )
    auth_header = create_admin_authorization_header()
    resp = client.post(
        f"/service/{sample_template.service.id}/template/{sample_template.id}",
        headers=[("Content-Type", "application/json"), auth_header],
        data=json_data,
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert ("Content has a character count greater than the limit of {}").format(
        SMS_CHAR_COUNT_LIMIT
    ) in json_resp["message"]["content"]


def test_should_return_all_template_versions_for_service_and_template_id(
    client, sample_template
):
    original_content = sample_template.content
    from app.dao.templates_dao import dao_update_template

    sample_template.content = original_content + "1"
    dao_update_template(sample_template)
    sample_template.content = original_content + "2"
    dao_update_template(sample_template)

    auth_header = create_admin_authorization_header()
    resp = client.get(
        f"/service/{sample_template.service_id}/template/{sample_template.id}/versions",
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 200
    resp_json = json.loads(resp.get_data(as_text=True))["data"]
    assert len(resp_json) == 3
    for x in resp_json:
        if x["version"] == 1:
            assert x["content"] == original_content
        elif x["version"] == 2:
            assert x["content"] == original_content + "1"
        else:
            assert x["content"] == original_content + "2"


def test_update_does_not_create_new_version_when_there_is_no_change(
    client, sample_template
):
    auth_header = create_admin_authorization_header()
    data = {
        "template_type": sample_template.template_type,
        "content": sample_template.content,
    }
    resp = client.post(
        f"/service/{sample_template.service_id}/template/{sample_template.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 200

    template = dao_get_template_by_id(sample_template.id)
    assert template.version == 1


def test_update_set_process_type_on_template(client, sample_template):
    auth_header = create_admin_authorization_header()
    data = {"process_type": TemplateProcessType.PRIORITY}
    resp = client.post(
        f"/service/{sample_template.service_id}/template/{sample_template.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 200

    template = dao_get_template_by_id(sample_template.id)
    assert template.process_type == TemplateProcessType.PRIORITY


@pytest.mark.parametrize(
    "post_data, expected_errors",
    [
        (
            {},
            [
                {
                    "error": "ValidationError",
                    "message": "subject is a required property",
                },
                {"error": "ValidationError", "message": "name is a required property"},
                {
                    "error": "ValidationError",
                    "message": "template_type is a required property",
                },
                {
                    "error": "ValidationError",
                    "message": "content is a required property",
                },
                {
                    "error": "ValidationError",
                    "message": "service is a required property",
                },
                {
                    "error": "ValidationError",
                    "message": "created_by is a required property",
                },
            ],
        )
    ],
)
def test_create_template_validates_against_json_schema(
    admin_request,
    sample_service_full_permissions,
    post_data,
    expected_errors,
):
    response = admin_request.post(
        "template.create_template",
        service_id=sample_service_full_permissions.id,
        _data=post_data,
        _expected_status=400,
    )
    assert response["errors"] == expected_errors


def test_update_redact_template(admin_request, sample_template):
    assert sample_template.redact_personalisation is False

    data = {
        "redact_personalisation": True,
        "created_by": str(sample_template.created_by_id),
    }

    dt = datetime.now()

    with freeze_time(dt):
        resp = admin_request.post(
            "template.update_template",
            service_id=sample_template.service_id,
            template_id=sample_template.id,
            _data=data,
        )

    assert resp is None

    assert sample_template.redact_personalisation is True
    assert (
        sample_template.template_redacted.updated_by_id == sample_template.created_by_id
    )
    assert sample_template.template_redacted.updated_at == dt

    assert sample_template.version == 1


def test_update_redact_template_ignores_other_properties(
    admin_request, sample_template
):
    data = {
        "name": "Foo",
        "redact_personalisation": True,
        "created_by": str(sample_template.created_by_id),
    }

    admin_request.post(
        "template.update_template",
        service_id=sample_template.service_id,
        template_id=sample_template.id,
        _data=data,
    )

    assert sample_template.redact_personalisation is True
    assert sample_template.name != "Foo"


def test_update_redact_template_does_nothing_if_already_redacted(
    admin_request, sample_template
):
    dt = datetime.now()
    with freeze_time(dt):
        dao_redact_template(sample_template, sample_template.created_by_id)

    data = {
        "redact_personalisation": True,
        "created_by": str(sample_template.created_by_id),
    }

    with freeze_time(dt + timedelta(days=1)):
        resp = admin_request.post(
            "template.update_template",
            service_id=sample_template.service_id,
            template_id=sample_template.id,
            _data=data,
        )

    assert resp is None

    assert sample_template.redact_personalisation is True
    # make sure that it hasn't been updated
    assert sample_template.template_redacted.updated_at == dt


def test_update_redact_template_400s_if_no_created_by(admin_request, sample_template):
    original_updated_time = sample_template.template_redacted.updated_at
    resp = admin_request.post(
        "template.update_template",
        service_id=sample_template.service_id,
        template_id=sample_template.id,
        _data={"redact_personalisation": True},
        _expected_status=400,
    )

    assert resp == {"result": "error", "message": {"created_by": ["Field is required"]}}

    assert sample_template.redact_personalisation is False
    assert sample_template.template_redacted.updated_at == original_updated_time
