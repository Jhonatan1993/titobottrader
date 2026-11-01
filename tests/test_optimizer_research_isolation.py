import json
from optimizer import GridSearchOptimizer


def test_empty_data_never_writes_active_parameters(tmp_path, monkeypatch):
    optimizer = GridSearchOptimizer.__new__(GridSearchOptimizer)
    active = tmp_path / "optimal_params.json"
    active.write_text('{"original": true}', encoding="utf-8")
    optimizer.output_file = str(tmp_path / "experimental_optimizer_results.json")
    optimizer.optimal_configs = {}
    monkeypatch.setattr(optimizer, "connect", lambda: False)
    optimizer.run(assets=["EURUSD"])
    assert json.loads(active.read_text(encoding="utf-8")) == {"original": True}
    result = json.loads((tmp_path / "experimental_optimizer_results.json").read_text(encoding="utf-8"))
    assert result["EURUSD"]["win_rate"] is None
    assert result["EURUSD"]["validation_status"] == "insufficient_data"
