from typing import Dict, List

class PortfolioManager:
    def __init__(self):
        self.positions: Dict[str, Dict] = {}

    def add_position(self, position: Dict):
        self.positions[position["id"]] = position

    def close_position(self, position_id: str):
        if position_id in self.positions:
            self.positions[position_id]["status"] = "CLOSED"
            return self.positions[position_id]
        return None

    def get_open_positions(self) -> List[Dict]:
        return [pos for pos in self.positions.values() if pos["status"] == "OPEN"]

    def get_all_positions(self) -> List[Dict]:
        return list(self.positions.values())

    def remove_position(self, position_id: str):
        if position_id in self.positions:
            del self.positions[position_id]
