import re
from pydantic import BaseModel, Field, model_validator

CODE = re.compile(r'^[A-Z]{2,5} \d{4}[A-Z]?$')
GRADES = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0, 'P': None, 'TR': None}

class AcademicState(BaseModel):
    completed: dict[str, str] = Field(default_factory=dict)
    in_progress: list[str] = Field(default_factory=list)
    applied_credits: float = Field(default=0, ge=0, le=250)
    gpa: float | None = Field(default=None, ge=0, le=4)
    reviewed: bool = False
    # Explicit student confirmation of categorical requirements not inferred from PDF.
    satisfied_groups: list[str] = Field(default_factory=list)
    requirement_choices: dict[str, list[str]] = Field(default_factory=dict)
    approved_exceptions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_codes(self):
        codes = list(self.completed) + self.in_progress
        if len(codes) > 200 or any(not CODE.fullmatch(c) for c in codes):
            raise ValueError('Use canonical course codes such as ITSC 1212 (maximum 200 courses).')
        if len(set(self.in_progress)) != len(self.in_progress) or set(self.completed) & set(self.in_progress):
            raise ValueError('Completed and in-progress courses must be distinct.')
        if any(g not in GRADES for g in self.completed.values()):
            raise ValueError('Grades must be A, B, C, D, F, P, or TR; unknown transfer grades require review.')
        if len(self.satisfied_groups) > 100 or len(self.approved_exceptions) > 100:
            raise ValueError('Too many requirement confirmations.')
        return self

class Preferences(BaseModel):
    career: str = '15-1252.00'
    start_year: int = Field(default=2027, ge=2026, le=2040)
    start_term: str = 'Fall'
    target_year: int | None = Field(default=None, ge=2026, le=2045)
    target_term: str = 'Spring'
    min_credits: int = Field(default=12, ge=0, le=21)
    max_credits: int = Field(default=15, ge=1, le=21)
    min_courses: int = Field(default=4, ge=0, le=7)
    max_courses: int = Field(default=5, ge=1, le=7)
    pinned: dict[str, int] = Field(default_factory=dict)
    preferred: list[str] = Field(default_factory=list)
    variable_credits: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check(self):
        if self.start_term not in ['Fall', 'Spring'] or self.target_term not in ['Fall', 'Spring']:
            raise ValueError('Terms must be Fall or Spring.')
        if self.min_credits > self.max_credits or self.min_courses > self.max_courses:
            raise ValueError('Minimum limits cannot exceed maximum limits.')
        if len(self.pinned) > 100 or any(not CODE.fullmatch(k) or not 0 <= v < 16 for k, v in self.pinned.items()):
            raise ValueError('Pinned courses need canonical codes and semester indices 0–15.')
        if any(not CODE.fullmatch(k) for k in self.preferred + list(self.variable_credits)):
            raise ValueError('Preference course codes are invalid.')
        return self
