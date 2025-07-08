from unittest.mock import MagicMock

from app.history_meta import (
    _get_bases_for_versioned_class,
    _handle_single_table_inheritance,
)


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

    assert bases == (object,)
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


def test_handle_single_table_inheritance():
    col1 = MagicMock()
    col1.key = "id"
    col1.name = "name_col1"
    col2 = MagicMock()
    col2.key = "new_column"
    col2.name = "name_col2"

    local_mapper = MagicMock()
    local_mapper.local_table.c = [col1, col2]

    super_history_mapper = MagicMock()
    super_history_mapper.local_table.c = {"id": col1}
    super_history_mapper.local_table.append_column = col2

    _handle_single_table_inheritance(local_mapper, super_history_mapper)

    super_history_mapper.local_table.append_column.assert_called_once()
