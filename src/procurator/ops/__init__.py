from .base import Operation
from .convert import CbrToCbz, ConvertImages
from .dedupe import MoveDuplicates
from .move import MoveToFolder
from .organize import AiOrganize
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
    "AiOrganize",
    "Append",
    "CbrToCbz",
    "ChangeCase",
    "ConvertImages",
    "DateStamp",
    "InsertChars",
    "MoveDuplicates",
    "MoveToFolder",
    "Operation",
    "Prepend",
    "RegexReplace",
    "RemoveChars",
    "ReplaceText",
    "Sequence",
    "Wildcard",
]
