import pytest
from flask import json

from app.models import TemplateType
from tests import create_service_authorization_header
from tests.app.db import create_template


def test_get_all_templates_returns_200(client, sample_service):
    templates = [
        create_template(
            sample_service,
            template_type=tmp_type,
            subject=f"subject_{name}" if tmp_type == TemplateType.EMAIL else "",
            template_name=name,
        )
        for name, tmp_type in (("A", TemplateType.SMS), ("B", TemplateType.EMAIL))
    ]

    auth_header = create_service_authorization_header(service_id=sample_service.id)

    response = client.get(
        path="/v2/templates",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response["templates"]) == len(templates)

    for index, template in enumerate(json_response["templates"]):
        assert template["id"] == str(templates[index].id)
        assert template["body"] == templates[index].content
        assert template["type"] == templates[index].template_type
        if templates[index].template_type == TemplateType.EMAIL:
            assert template["subject"] == templates[index].subject


@pytest.mark.parametrize("tmp_type", (TemplateType.SMS, TemplateType.EMAIL))
def test_get_all_templates_for_valid_type_returns_200(client, sample_service, tmp_type):
    templates = [
        create_template(
            sample_service,
            template_type=tmp_type,
            template_name=f"Template {i}",
            subject=f"subject_{i}" if tmp_type == TemplateType.EMAIL else "",
        )
        for i in range(3)
    ]

    auth_header = create_service_authorization_header(service_id=sample_service.id)

    response = client.get(
        path=f"/v2/templates?type={tmp_type}",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response["templates"]) == len(templates)

    for index, template in enumerate(json_response["templates"]):
        assert template["id"] == str(templates[index].id)
        assert template["body"] == templates[index].content
        assert template["type"] == tmp_type
        if templates[index].template_type == TemplateType.EMAIL:
            assert template["subject"] == templates[index].subject


@pytest.mark.parametrize("tmp_type", (TemplateType.SMS, TemplateType.EMAIL))
def test_get_correct_num_templates_for_valid_type_returns_200(
    client, sample_service, tmp_type
):
    num_templates = 3

    templates = []
    for _ in range(num_templates):
        templates.append(create_template(sample_service, template_type=tmp_type))

    for other_type in TemplateType:
        if other_type != tmp_type:
            templates.append(create_template(sample_service, template_type=other_type))

    auth_header = create_service_authorization_header(service_id=sample_service.id)

    response = client.get(
        path=f"/v2/templates?type={tmp_type}",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response["templates"]) == num_templates


def test_get_all_templates_for_invalid_type_returns_400(client, sample_service):
    auth_header = create_service_authorization_header(service_id=sample_service.id)

    invalid_type = "coconut"

    response = client.get(
        path=f"/v2/templates?type={invalid_type}",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 400
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))

    type_str = ", ".join(
        [f"<{type(e).__name__}.{e.name}: {e.value}>" for e in TemplateType]
    )
    assert json_response == {
        "status_code": 400,
        "errors": [
            {
                "message": f"type coconut is not one of [{type_str}]",
                "error": "ValidationError",
            }
        ],
    }
