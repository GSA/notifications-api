from base64 import urlsafe_b64encode
from json import dumps, loads

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from itsdangerous import BadSignature, URLSafeSerializer


class EncryptionError(Exception):
    pass


class SaltLengthError(Exception):
    pass


class Encryption:
    def init_app(self, app):
        self._serializer = URLSafeSerializer(app.config.get("SECRET_KEY"))
        self._salt = app.config.get("DANGEROUS_SALT")
        self._password = app.config.get("SECRET_KEY").encode()

        try:
            self._shared_encryptor = Fernet(self._derive_key(self._salt))
        except SaltLengthError as reason:
            raise EncryptionError(
                "DANGEROUS_SALT must be at least 16 bytes"
            ) from reason

    def encrypt(self, thing_to_encrypt, salt=None):
        """Encrypt a string or object

        thing_to_encrypt must be serializable as JSON
        Returns a UTF-8 string
        """
        serialized_bytes = dumps(thing_to_encrypt).encode("utf-8")
        encrypted_bytes = self._encryptor(salt).encrypt(serialized_bytes)
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, thing_to_decrypt, salt=None):
        """Decrypt a UTF-8 string or bytes.

        Once decrypted, thing_to_decrypt must be deserializable from JSON.
        """
        try:
            return loads(self._encryptor(salt).decrypt(thing_to_decrypt))
        except InvalidToken as reason:
            raise EncryptionError from reason

    def sign(self, thing_to_sign, salt=None):
        return self._serializer.dumps(thing_to_sign, salt=(salt or self._salt))

    def verify_signature(self, thing_to_verify, salt=None):
        try:
            return self._serializer.loads(thing_to_verify, salt=(salt or self._salt))
        except BadSignature as reason:
            raise EncryptionError from reason

    def _encryptor(self, salt=None):
        if salt is None:
            return self._shared_encryptor
        else:
            try:
                return Fernet(self._derive_key(salt))
            except SaltLengthError as reason:
                raise EncryptionError(
                    "Custom salt value must be at least 16 bytes"
                ) from reason

    def _derive_key(self, salt):
        """Derive a key suitable for use within Fernet from the SECRET_KEY and salt

        * For the salt to be secure, it must be 16 bytes or longer and randomly generated.
        * 600_000 was chosen for the iterations because it is what OWASP recommends as
        *  of [February 2023](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2)
        * For more information, see https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#pbkdf2
        * and https://cryptography.io/en/latest/fernet/#using-passwords-with-fernet
        """
        salt_bytes = salt.encode()
        if len(salt_bytes) < 16:
            raise SaltLengthError
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt_bytes, iterations=600_000
        )
        return urlsafe_b64encode(kdf.derive(self._password))
