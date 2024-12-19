from sqlalchemy import delete, select

from app import db
from app.dao import DAOClass
from app.enums import PermissionType
from app.models import Permission, Service


class PermissionDAO(DAOClass):
    class Meta:
        model = Permission

    def add_default_service_permissions_for_user(self, user, service):
        for name in PermissionType.defaults():
            permission = Permission(permission=name, user=user, service=service)
            self.create_instance(permission, _commit=False)

    def remove_user_service_permissions(self, user, service):
        db.session.execute(
            delete(self.Meta.model).where(
                self.Meta.model.user == user, self.Meta.model.service == service
            )
        )
        db.session.commit()

    def remove_user_service_permissions_for_all_services(self, user):
        db.session.execute(delete(self.Meta.model).where(self.Meta.model.user == user))
        db.session.commit()

    def set_user_service_permission(
        self, user, service, permissions, _commit=False, replace=False
    ):
        try:
            if replace:
                db.session.execute(
                    delete(self.Meta.model).where(
                        self.Meta.model.user == user, self.Meta.model.service == service
                    )
                )

                db.session.commit()
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
            db.session.execute(
                select(self.Meta.model)
                .where(self.Meta.model.user_id == user_id)
                .join(Permission)
                .join(Service, Permission.service_id == Service.id)
                .where(Service.active == True)  # noqa
            )
            .scalars()
            .all()
        )

    def get_permissions_by_user_id_and_service_id(self, user_id, service_id):
        return (
            db.session.execute(
                select(self.Meta.model)
                .where(self.Meta.model.user_id == user_id)
                .join(Permission.service)
                .where(
                    Permission.service.active == True,  # noqa
                    Permission.service.id == service_id,
                )  # noqa
            )
            .scalars()
            .all()
        )


permission_dao = PermissionDAO()
