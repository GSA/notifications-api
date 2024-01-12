from app import db
from app.dao import DAOClass
from app.enums import PermissionType
from app.models import Permission


class PermissionDAO(DAOClass):
    class Meta:
        model = Permission

    def add_default_service_permissions_for_user(self, user, service):
        for name in PermissionType.defaults:
            permission = Permission(permission=name, user=user, service=service)
            self.create_instance(permission, _commit=False)

    def remove_user_service_permissions(self, user, service):
        query = self.Meta.model.query.filter_by(user=user, service=service)
        query.delete()

    def remove_user_service_permissions_for_all_services(self, user):
        query = self.Meta.model.query.filter_by(user=user)
        query.delete()

    def set_user_service_permission(
        self, user, service, permissions, _commit=False, replace=False
    ):
        try:
            if replace:
                query = self.Meta.model.query.filter_by(user=user, service=service)
                query.delete()
            for p in permissions:
                p.user = user
                p.service = service
                self.create_instance(p, _commit=False)
        except Exception as e:
            if _commit:
                db.session.rollback()
            raise e
        else:
            if _commit:
                db.session.commit()

    def get_permissions_by_user_id(self, user_id):
        return (
            self.Meta.model.query.filter_by(user_id=user_id)
            .join(Permission.service)
            .filter_by(active=True)
            .all()
        )

    def get_permissions_by_user_id_and_service_id(self, user_id, service_id):
        return (
            self.Meta.model.query.filter_by(user_id=user_id)
            .join(Permission.service)
            .filter_by(active=True, id=service_id)
            .all()
        )


permission_dao = PermissionDAO()
