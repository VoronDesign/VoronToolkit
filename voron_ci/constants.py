from enum import Enum
from typing import NamedTuple

SUCCESS_LABEL: str = "PR: CI passed"
PR_COMMENT_TAG: str = "<!-- voron_docker_toolkit -->"


class StepResultCodeStr(NamedTuple):
    result_code: int
    result_str: str


class StepIdName(NamedTuple):
    step_id: str
    step_name: str
    step_pr_label: str


class StepResult(StepResultCodeStr, Enum):
    SUCCESS = StepResultCodeStr(result_code=0, result_str="✅ SUCCESS")
    WARNING = StepResultCodeStr(result_code=1, result_str="⚠️ WARNING")
    FAILURE = StepResultCodeStr(result_code=2, result_str="❌ FAILURE")
    EXCEPTION = StepResultCodeStr(result_code=3, result_str="💀 EXCEPTION")


class StepIdentifier(StepIdName, Enum):
    WHITESPACE_CHECK = StepIdName(step_id="whitespace_check", step_name="Whitespace checker", step_pr_label="Issue: Whitespace")
    ROTATION_CHECK = StepIdName(step_id="rotation_check", step_name="STL rotation checker", step_pr_label="Issue: STL Rotation")
    CORRUPTION_CHECK = StepIdName(step_id="corruption_check", step_name="STL corruption checker", step_pr_label="Issue: STL Corruption")
    README_GENERATOR = StepIdName(step_id="readme_generator", step_name="Readme generator", step_pr_label="Issue: Readme")
    MOD_STRUCTURE_CHECK = StepIdName(step_id="mod_structure_check", step_name="Mod structure checker", step_pr_label="Issue: Mod Structure")


VORONUSERS_PR_COMMENT_SECTIONS: list[StepIdentifier] = [
    StepIdentifier.WHITESPACE_CHECK,
    StepIdentifier.MOD_STRUCTURE_CHECK,
    StepIdentifier.CORRUPTION_CHECK,
    StepIdentifier.ROTATION_CHECK,
]
