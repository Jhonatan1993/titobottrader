from typing import Dict, List
from execution.engine import ExecutionEngine
import uuid
import datetime

class PaperExecutionEngine(ExecutionEngine):
    def __init__(self):
        self.open_positions: Dict[str, Dict] = {}
        self.closed_positions: Dict[str, Dict] = {}
        self.balance = 10000.0  # default starting balance

    def open_position(self, order: Dict) -> Dict:
        position_id = str(uuid.uuid4())
        order["id"] = position_id
        order["timestamp"] = datetime.datetime.utcnow().isoformat()
        order["status"] = "OPEN"
        self.open_positions[position_id] = order
        return {"success": True, "position": order}

    def close_position(self, position_id: str) -> Dict:
        if position_id in self.open_positions:
            position = self.open_positions.pop(position_id)
            position["status"] = "CLOSED"
            position["close_timestamp"] = datetime.datetime.utcnow().isoformat()
            self.closed_positions[position_id] = position
            return {"success": True, "position": position}
        return {"success": False, "error": "Position not found"}

    def cancel_order(self, order_id: str) -> Dict:
        # Paper trading doesn't differentiate orders for now
        return {"success": True, "message": "No real orders to cancel in paper trading"}

    def get_open_positions(self) -> List[Dict]:
        return list(self.open_positions.values())

    def get_account_balance(self) -> float:
        return self.balance

    def get_order_status(self, order_id: str) -> Dict:
        if order_id in self.open_positions:
            return {"status": "OPEN", "order": self.open_positions[order_id]}
        if order_id in self.closed_positions:
            return {"status": "CLOSED", "order": self.closed_positions[order_id]}
        return {"status": "UNKNOWN", "order": None}
