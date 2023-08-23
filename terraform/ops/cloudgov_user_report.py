from subprocess import check_output

from cloudfoundry_client.client import CloudFoundryClient

ORG_NAME = "gsa-tts-benefits-studio-prototyping"


client = CloudFoundryClient.build_from_cf_config()
org_guid = check_output(f"cf org {ORG_NAME} --guid", shell=True).decode().strip()
space_guids = list(
    map(lambda item: item["guid"], client.v3.spaces.list(organization_guids=org_guid))
)


class RoleCollector:
    def __init__(self):
        self._map = {}

    def add(self, role):
        user = role.user
        if self._map.get(user.guid) is None:
            self._map[user.guid] = {"user": user, "roles": [role]}
        else:
            self._map[user.guid]["roles"].append(role)

    def print(self):
        for user_roles in self._map.values():
            user = user_roles["user"]
            print(f"{user.type}: {user.username} has roles:")
            for role in user_roles["roles"]:
                if role.space:
                    print(f"  {role.type} in {role.space.name}")
                else:
                    print(f"  {role.type}")


role_collector = RoleCollector()


class User:
    def __init__(self, entity):
        self.guid = entity["guid"]
        self._username = entity["username"]
        self._is_service_account = entity["origin"] != "gsa.gov"
        self.type = "Bot" if self._is_service_account else "User"

    @property
    def username(self):
        if self._is_service_account:
            return client.v3.service_credential_bindings.get(
                self._username, include="service_instance"
            ).service_instance()["name"]
        else:
            return self._username


class Space:
    def __init__(self, entity):
        self.name = entity["name"]


class Role:
    def __init__(self, entity):
        self._fields = entity
        self.type = entity["type"]
        self.user = User(entity.user())

    @property
    def space(self):
        try:
            return Space(self._fields.space())
        except AttributeError:
            return None


for role in map(
    Role, client.v3.roles.list(organization_guids=org_guid, include="user")
):
    role_collector.add(role)
for role in map(Role, client.v3.roles.list(space_guids=space_guids, include="user")):
    role_collector.add(role)


if __name__ == "__main__":
    role_collector.print()
