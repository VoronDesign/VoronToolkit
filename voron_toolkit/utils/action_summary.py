from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self


class ActionSummary(ABC):
    @abstractmethod
    def to_markdown(self: Self, *, result_ok: bool = True) -> str:
        pass


@dataclass
class ActionSummaryTable(ActionSummary):
    columns: list[str]
    rows: list[list[str]]

    def to_markdown(self: Self, *, result_ok: bool = True) -> str:
        return (
            f"<details{' open' if not result_ok else ''}>\n"
            f"<summary>Result (items: {len(self.rows)})</summary>\n\n"
            f"{self.create_markdown_table(self.columns, self.rows)}\n"
            f"</details>\n"
        )

    @classmethod
    def _create_table_header(cls: type[Self], columns: list[str]) -> str:
        column_names = "| " + " | ".join(columns) + " |"
        dividers = "| " + " | ".join(["---"] * len(columns)) + " |"
        return f"{column_names}\n{dividers}"

    @classmethod
    def _create_markdown_table_rows(cls: type[Self], rows: list[list[str]]) -> str:
        return "\n".join(["| " + " | ".join(row_elements) + " |" for row_elements in rows])

    @classmethod
    def create_markdown_table(cls: type[Self], columns: list[str], rows: list[list[str]]) -> str:
        return f"{cls._create_table_header(columns=columns)}\n{cls._create_markdown_table_rows(rows=rows)}\n"
