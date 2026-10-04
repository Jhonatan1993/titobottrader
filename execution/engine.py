from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class ExecutionEngine(ABC):
    @abstractmethod
    def open_position(self, order: Dict) -> Dict:
        pass

    @abstractmethod
    def close_position(self, position_id: str) -> Dict:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict:
        pass

    @abstractmethod
    def get_open_positions(self) -> List[Dict]:
        pass

    @abstractmethod
    def get_account_balance(self) -> float:
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict:
        pass
