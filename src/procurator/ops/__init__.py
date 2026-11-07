from .base import Operation
from .convert import CbrToCbz, ConvertImages
from .dedupe import MoveDuplicates
from .move import MoveToFolder, SortByTemplate
from .organize import AiOrganize
from .rename import (
    Append,
    ChangeCase,
    DateStamp,
    InsertChars,
    NameTemplate,
    Prepend,
    RegexReplace,
    RemoveChars,
    ReplaceText,
    Sequence,
    Wildcard,
)
from .trash import TrashDuplicates

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
    "NameTemplate",
    "Operation",
    "Prepend",
    "RegexReplace",
    "RemoveChars",
    "ReplaceText",
    "Sequence",
    "TrashDuplicates",
    "SortByTemplate",
    "Wildcard",
]
