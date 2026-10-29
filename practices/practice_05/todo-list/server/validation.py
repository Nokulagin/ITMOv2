"""Validation rules for task fields. No database and no HTTP here."""

from __future__ import annotations

from typing import Any

MAX_TITLE_LENGTH = 200

# Russian texts are copied from specs/001-todo-list/contract.md, section 4.
ERROR_TITLE_NOT_STRING = "Название задачи должно быть строкой."
ERROR_TITLE_EMPTY = "Название задачи не может быть пустым."
ERROR_TITLE_TOO_LONG = "Название задачи не должно быть длиннее 200 символов."
ERROR_DONE_NOT_BOOL = "Поле done должно быть true или false."


class ValidationError(Exception):
    """Client input breaks a rule. `message` is the Russian text from the contract."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def normalize_title(value: Any) -> str:
    """Return the title with outer whitespace removed, or raise ValidationError.

    Length is counted in Unicode code points (Python str length), after stripping.
    """
    if not isinstance(value, str):
        raise ValidationError(ERROR_TITLE_NOT_STRING)
    title = value.strip()
    if not title:
        raise ValidationError(ERROR_TITLE_EMPTY)
    if len(title) > MAX_TITLE_LENGTH:
        raise ValidationError(ERROR_TITLE_TOO_LONG)
    return title


def validate_done(value: Any) -> bool:
    """Accept only JSON booleans. Numbers such as 1 and strings such as "true" are rejected."""
    if not isinstance(value, bool):
        raise ValidationError(ERROR_DONE_NOT_BOOL)
    return value
