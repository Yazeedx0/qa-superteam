"""Dependency-free (de)serialization and JSON Schema generation for dataclass models.

QA Superteam's core deliberately avoids third-party runtime dependencies so the
``qast`` CLI can run with any Python >= 3.11 without installing packages into the
project under test.  This module provides the three operations the models need:

* ``to_dict``      dataclass -> JSON-compatible dict (enums become their values)
* ``from_dict``    dict -> dataclass, with strict type checking and precise error paths
* ``json_schema``  dataclass -> JSON Schema (draft 2020-12)

Only the type constructs used by :mod:`qa_superteam.models` are supported:
``str``, ``int``, ``float``, ``bool``, ``Any``, ``X | None``, ``list[X]``,
``dict[str, X]``, ``Enum`` subclasses and nested dataclasses.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from typing import Any, get_args, get_origin, get_type_hints

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


class SchemaError(ValueError):
    """Raised when data does not conform to a model."""

    def __init__(self, path: str, message: str):
        self.path = path or "$"
        self.message = message
        super().__init__(f"{self.path}: {message}")


def _is_optional(tp: Any) -> tuple[bool, Any]:
    origin = get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1 and len(get_args(tp)) == 2:
            return True, args[0]
    return False, tp


def to_dict(obj: Any) -> Any:
    """Convert a dataclass tree into JSON-compatible primitives."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            out[f.name] = to_dict(getattr(obj, f.name))
        return out
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    return obj


def from_dict(cls: type, data: Any, path: str = "$") -> Any:
    """Build ``cls`` from ``data`` validating every field. Unknown keys are rejected."""
    return _coerce(cls, data, path)


def _coerce(tp: Any, value: Any, path: str) -> Any:
    optional, inner = _is_optional(tp)
    if value is None:
        if optional or tp is Any:
            return None
        raise SchemaError(path, "must not be null")
    tp = inner

    if tp is Any:
        return value
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        try:
            return tp(value)
        except ValueError:
            allowed = ", ".join(repr(m.value) for m in tp)
            raise SchemaError(path, f"{value!r} is not one of {allowed}") from None
    if dataclasses.is_dataclass(tp):
        if not isinstance(value, dict):
            raise SchemaError(path, f"expected object for {tp.__name__}, got {type(value).__name__}")
        hints = get_type_hints(tp)
        fields = {f.name: f for f in dataclasses.fields(tp)}
        unknown = sorted(set(value) - set(fields))
        if unknown:
            raise SchemaError(path, f"unknown field(s) for {tp.__name__}: {', '.join(unknown)}")
        kwargs = {}
        for name, f in fields.items():
            if name in value:
                kwargs[name] = _coerce(hints[name], value[name], f"{path}.{name}")
            elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                raise SchemaError(f"{path}.{name}", f"required field missing for {tp.__name__}")
        obj = tp(**kwargs)
        validator = getattr(obj, "_validate", None)
        if callable(validator):
            problem = validator()
            if problem:
                raise SchemaError(path, problem)
        return obj
    origin = get_origin(tp)
    if origin is list:
        if not isinstance(value, list):
            raise SchemaError(path, f"expected array, got {type(value).__name__}")
        (item_tp,) = get_args(tp)
        return [_coerce(item_tp, v, f"{path}[{i}]") for i, v in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise SchemaError(path, f"expected object, got {type(value).__name__}")
        _, val_tp = get_args(tp)
        return {str(k): _coerce(val_tp, v, f"{path}.{k}") for k, v in value.items()}
    if tp is bool:
        if not isinstance(value, bool):
            raise SchemaError(path, f"expected boolean, got {type(value).__name__}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaError(path, f"expected integer, got {type(value).__name__}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaError(path, f"expected number, got {type(value).__name__}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise SchemaError(path, f"expected string, got {type(value).__name__}")
        return value
    raise TypeError(f"unsupported type {tp!r} at {path}")


def _schema_for(tp: Any, defs: dict[str, Any]) -> dict[str, Any]:
    optional, inner = _is_optional(tp)
    if optional:
        return {"anyOf": [_schema_for(inner, defs), {"type": "null"}]}
    if tp is Any:
        return {}
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        name = tp.__name__
        if name not in defs:
            defs[name] = {"type": "string", "enum": [m.value for m in tp]}
            if tp.__doc__:
                defs[name]["description"] = tp.__doc__.strip()
        return {"$ref": f"#/$defs/{name}"}
    if dataclasses.is_dataclass(tp):
        name = tp.__name__
        if name not in defs:
            defs[name] = {}  # placeholder guards recursion
            defs[name] = _object_schema(tp, defs)
        return {"$ref": f"#/$defs/{name}"}
    origin = get_origin(tp)
    if origin is list:
        (item_tp,) = get_args(tp)
        return {"type": "array", "items": _schema_for(item_tp, defs)}
    if origin is dict:
        _, val_tp = get_args(tp)
        return {"type": "object", "additionalProperties": _schema_for(val_tp, defs)}
    mapping = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if tp in mapping:
        return {"type": mapping[tp]}
    raise TypeError(f"unsupported type {tp!r}")


def _object_schema(cls: type, defs: dict[str, Any]) -> dict[str, Any]:
    hints = get_type_hints(cls)
    props: dict[str, Any] = {}
    required: list[str] = []
    for f in dataclasses.fields(cls):
        prop = _schema_for(hints[f.name], defs)
        doc = f.metadata.get("doc") if f.metadata else None
        if doc:
            prop = {**prop, "description": doc}
        props[f.name] = prop
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    if cls.__doc__ and not cls.__doc__.startswith(cls.__name__ + "("):
        schema["description"] = " ".join(cls.__doc__.split())
    return schema


def json_schema(cls: type, schema_id: str | None = None) -> dict[str, Any]:
    """Return a standalone JSON Schema document for a dataclass model."""
    defs: dict[str, Any] = {}
    root = _object_schema(cls, defs)
    defs.pop(cls.__name__, None)
    doc: dict[str, Any] = {"$schema": SCHEMA_DRAFT}
    if schema_id:
        doc["$id"] = schema_id
    doc["title"] = cls.__name__
    doc.update(root)
    if defs:
        doc["$defs"] = dict(sorted(defs.items()))
    return doc


def field(doc: str | None = None, **kwargs: Any) -> Any:
    """``dataclasses.field`` with an optional documentation string used in schemas."""
    metadata = dict(kwargs.pop("metadata", {}) or {})
    if doc:
        metadata["doc"] = doc
    return dataclasses.field(metadata=metadata, **kwargs)
