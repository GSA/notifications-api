from unittest.mock import MagicMock

from app.history_meta import _get_bases_for_versioned_class


def test_get_bases_with_super_history_and_table():
    mock_super_mapper = MagicMock()
    mock_super_mapper.class_ = object
    mock_super_mapper.attrs.changed.columns = ["col1", "col2"]
    mock_table = MagicMock()
    mock_table.c.changed = "changed_col"

    properties = {}
    bases = _get_bases_for_versioned_class(
        super_history_mapper=mock_super_mapper,
        table=mock_table,
        properties=properties,
        local_mapper=None,
    )

    assert bases == [
        object,
    ]
    assert properties["changed"] == ("changed_col", "col1", "col2")


def test_get_bases_with_super_history_and_no_table():
    mock_super_mapper = MagicMock()
    mock_super_mapper.class_ = int
    properties = {}
    bases = _get_bases_for_versioned_class(
        super_history_mapper=mock_super_mapper,
        table=None,
        properties=properties,
        local_mapper=None,
    )
    assert bases == (int,)
    assert "changed" not in properties


def test_get_bases_without_super_history():
    class Base:
        pass

    class_ = type("Dummy", (Base,), {})
    local_mapper = MagicMock()
    local_mapper.base_mapper.class_ = class_

    properties = {}

    bases = _get_bases_for_versioned_class(
        super_history_mapper=None,
        table=None,
        properties=properties,
        local_mapper=local_mapper,
    )

    assert bases == (Base,)
    assert "changed" not in properties
