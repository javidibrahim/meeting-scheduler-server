from pydantic import BaseModel, Field
from typing import List
from datetime import time
from enum import Enum

class Weekday(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

class AvailabilityWindow(BaseModel):
    weekday: Weekday
    start_time: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    end_time: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")

    def validate_times(self):
        start = time.fromisoformat(self.start_time)
        end = time.fromisoformat(self.end_time)
        if start >= end:
            raise ValueError("start_time must be before end_time")
        return True

class AvailabilityRequest(BaseModel):
    windows: List[AvailabilityWindow]

    def validate_all(self):
        for window in self.windows:
            window.validate_times()
        return True
