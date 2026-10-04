from dataclasses import dataclass, asdict
from typing import Dict


@dataclass(frozen=True)
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)
