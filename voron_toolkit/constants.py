import json
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple, Self

CI_PASSED_LABEL: str = "CI: Passed"
CI_FAILURE_LABEL: str = "CI: Issues identified"
CI_ERROR_LABEL: str = "Warning: CI Error"
PR_COMMENT_TAG: str = "<!-- voron_docker_toolkit -->"


class ExtendedResult(NamedTuple):
    code: int
    icon: str


class ExtendedResultEnum(ExtendedResult, Enum):
    SUCCESS = ExtendedResult(code=0, icon="✅")
    WARNING = ExtendedResult(code=1, icon="⚠️")
    FAILURE = ExtendedResult(code=2, icon="❌")
    EXCEPTION = ExtendedResult(code=3, icon="💀")


class ItemResult(NamedTuple):
    item: str
    extra_info: list[str]


@dataclass
class ToolSummaryTable:
    extra_columns: list[str]
    items: defaultdict[ExtendedResultEnum, list[ItemResult]]

    def to_markdown(self: Self, filter_result: ExtendedResultEnum | None = None) -> str:
        if filter_result:
            rows = [[row.item, *row.extra_info] for row in self.items[filter_result]]
            markdown: str = self.create_markdown_table(columns=["Item", *self.extra_columns], rows=rows) if rows else ""
        else:
            rows = [[row.item, f"{result.icon} {result.name}", *row.extra_info] for result in self.items for row in self.items[result]]
            markdown = self.create_markdown_table(columns=["Item", "Result", *self.extra_columns], rows=rows) if rows else ""
        return f"{markdown}"

    @classmethod
    def _create_table_header(cls: type[Self], columns: list[str]) -> str:
        column_names = "| " + " | ".join(columns) + " |"
        dividers = "| " + " | ".join(["---"] * len(columns)) + " |"
        return f"{column_names}\n{dividers}"

    @classmethod
    def _create_markdown_table_rows(cls: type[Self], rows: list[list[str]]) -> str:
        return "\n".join(["| " + " | ".join(row) + " |" for row in rows])

    @classmethod
    def create_markdown_table(cls: type[Self], columns: list[str], rows: list[list[str]]) -> str:
        return f"{cls._create_table_header(columns=columns)}\n{cls._create_markdown_table_rows(rows=rows)}\n"


@dataclass
class ToolResult:
    tool_id: str
    tool_name: str
    extended_result: ExtendedResultEnum
    tool_ignore_warnings: bool
    tool_result_items: ToolSummaryTable

    def to_json(self: Self) -> str:
        dct: dict[str, Any] = {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "extended_result": self.extended_result.name,
            "tool_ignore_warnings": self.tool_ignore_warnings,
            "tool_result_items_extra_columns": self.tool_result_items.extra_columns,
        }
        dct["tool_result_items"] = {}
        for extended_result in ExtendedResultEnum:
            dct["tool_result_items"][extended_result.name] = [
                {"item": itemresult.item, "extra_info": itemresult.extra_info} for itemresult in self.tool_result_items.items[extended_result]
            ]
        return json.dumps(dct, indent=4)

    @classmethod
    def from_json(cls: type[Self], json_string: str) -> Self:
        dct = json.loads(json_string)
        return cls(
            tool_id=dct.get("tool_id"),
            tool_name=dct.get("tool_name"),
            extended_result=ExtendedResultEnum[dct.get("extended_result")],
            tool_ignore_warnings=dct.get("tool_ignore_warnings"),
            tool_result_items=ToolSummaryTable(
                extra_columns=dct.get("tool_result_items_extra_columns"),
                items=defaultdict(
                    list,
                    {
                        extended_result: [
                            ItemResult(item=item_result["item"], extra_info=item_result["extra_info"])
                            for item_result in dct.get("tool_result_items").get(extended_result.name)
                        ]
                        for extended_result in ExtendedResultEnum
                    },
                ),
            ),
        )


class ToolIdentifier(NamedTuple):
    tool_id: str
    tool_name: str


class ToolIdentifierEnum(ToolIdentifier, Enum):
    CORRUPTION_CHECK = ToolIdentifier(tool_id="corruption_check", tool_name="STL corruption checker")
    MOD_STRUCTURE_CHECK = ToolIdentifier(tool_id="mod_structure_check", tool_name="Mod structure checker")
    README_GENERATOR = ToolIdentifier(tool_id="readme_generator", tool_name="Readme generator")
    ROTATION_CHECK = ToolIdentifier(tool_id="rotation_check", tool_name="STL rotation checker")
    WHITESPACE_CHECK = ToolIdentifier(tool_id="whitespace_check", tool_name="Whitespace checker")


VORONUSERS_PR_COMMENT_SECTIONS: list[ToolIdentifierEnum] = [
    ToolIdentifierEnum.WHITESPACE_CHECK,
    ToolIdentifierEnum.MOD_STRUCTURE_CHECK,
    ToolIdentifierEnum.CORRUPTION_CHECK,
    ToolIdentifierEnum.ROTATION_CHECK,
]
