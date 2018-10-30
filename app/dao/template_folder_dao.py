from app import db
from app.dao.dao_utils import transactional
from app.models import TemplateFolder


def dao_get_template_folder_by_id(template_folder_id):
    return TemplateFolder.query.filter(TemplateFolder.id == template_folder_id).one()


@transactional
def dao_create_template_folder(template_folder):
    db.session.add(template_folder)


@transactional
def dao_update_template_folder(template_folder):
    db.session.add(template_folder)


@transactional
def dao_delete_template_folder(template_folder):
    db.session.delete(template_folder)
