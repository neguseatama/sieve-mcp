"""The closed eight-word error vocabulary.

Every tool failure carries one word from ``CODES`` and one fixed short
sentence.  The sentence never embeds an exception text, a path or a
file name - the raw exception stays inside the server.
"""

CODES = (
    "path_not_allowed",
    "not_found",
    "not_a_regular_file",
    "too_large",
    "unsupported_type",
    "invalid_arguments",
    "run_failed",
    "read_not_allowed",
)

MESSAGES = {
    "path_not_allowed": "The path is not allowed.",
    "not_found": "The path does not exist.",
    "not_a_regular_file": "The path is not a regular file.",
    "too_large": "The file or the folder exceeds the size limits.",
    "unsupported_type": "The file type is not supported.",
    "invalid_arguments": "The tool arguments are invalid.",
    "run_failed": "The engine run failed.",
    "read_not_allowed": "Reading this file is not allowed.",
}


class ToolError(Exception):
    """One tool failure with a closed word and a fixed sentence."""

    def __init__(self, code: str, message: str | None = None):
        if code not in CODES:
            code = "run_failed"
        self.code = code
        self.message = message or MESSAGES[code]
        super().__init__(self.message)


class StartupError(Exception):
    """A startup violation (exit 2) with a fixed short sentence."""
