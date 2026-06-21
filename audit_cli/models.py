from pydantic import BaseModel

class TestResult(BaseModel):
    __test__ = False  # not a pytest test class
    unique_id: str
    status: str
    execution_time: float = 0.0
    message: str | None = None

class LineageNode(BaseModel):
    unique_id: str
    depends_on: list[str] = []

class EvidenceSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errored: int
