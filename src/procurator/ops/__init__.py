from .base import Operation
from .convert import CbrToCbz, ConvertImages
from .move import MoveToFolder
from .rename import (
    Append,
    ChangeCase,
    DateStamp,
    InsertChars,
    Prepend,
    RegexReplace,
    RemoveChars,
    ReplaceText,
    Sequence,
    Wildcard,
)

__all__ = [
    "Append",
    "CbrToCbz",
    "ChangeCase",
    "ConvertImages",
    "DateStamp",
    "InsertChars",
    "MoveToFolder",
    "Operation",
    "Prepend",
    "RegexReplace",
    "RemoveChars",
    "ReplaceText",
    "Sequence",
    "Wildcard",
]
