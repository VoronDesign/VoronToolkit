from enum import IntEnum, StrEnum


class ReturnStatus(IntEnum):
    SUCCESS = 0
    WARNING = 1
    FAILURE = 2
    EXCEPTION = 3


class SummaryStatus(StrEnum):
    SUCCESS = "✅ SUCCESS"
    WARNING = "⚠️ WARNING"
    FAILURE = "❌ FAILURE"
    EXCEPTION = "💀 EXCEPTION"


EXTENDED_OUTCOME: dict[ReturnStatus, str] = {
    ReturnStatus.SUCCESS: "success",
    ReturnStatus.WARNING: "warning",
    ReturnStatus.FAILURE: "failure",
    ReturnStatus.EXCEPTION: "exception",
}
