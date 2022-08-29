from pathlib import Path

from defusedxml.lxml import fromstring
# there is no equivalent in defusedxml to validate a schema
from lxml.etree import XMLSchema  # nosec B410


def validate_xml(document, schema_file_name):

    path = Path(__file__).resolve().parent / schema_file_name
    contents = path.read_text()

    schema_root = fromstring(contents.encode('utf-8'))
    schema = XMLSchema(schema_root)
    return schema.validate(fromstring(document))
