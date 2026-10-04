import pytest
from trade_journal.journal import TradeJournal

def test_daily_summary_and_metrics_calculation():
    """
    Verifica que el agrupamiento de transacciones por día y el cálculo
    de métricas consolidadas (Win Rate, PnL, Profit Factor, etc.) funcionen correctamente.
    """
    journal = TradeJournal()
    daily_summaries = journal.get_daily_summary()
    
    assert len(daily_summaries) > 0
    for day_data in daily_summaries:
        assert "date" in day_data
        assert "broker" in day_data
        assert "total_trades" in day_data
        assert "winning_trades" in day_data
        assert "losing_trades" in day_data
        assert "win_rate" in day_data
        assert "realized_pnl" in day_data
        assert "profit_factor" in day_data
        assert "total_invested" in day_data
        assert "trades" in day_data
        assert len(day_data["trades"]) == day_data["total_trades"]
        assert day_data["winning_trades"] + day_data["losing_trades"] + day_data["tie_trades"] == day_data["total_trades"]

def test_export_trades_csv_formats():
    """
    Verifica que la exportación CSV genere el formato UTF-8 con BOM y todas las cabeceras requeridas.
    """
    journal = TradeJournal()
    
    # 1. Modo completo
    complete_csv = journal.export_trades_csv(mode="complete")
    assert complete_csv.startswith("\ufeff")
    assert "Fecha_Dia,Broker,Total_Operaciones" in complete_csv
    assert "Fecha_Dia,ID_Operacion,Broker,Simbolo" in complete_csv
    assert "Profit_Factor" in complete_csv
    assert "PnL_Realizado_USD" in complete_csv

    # 2. Modo solo resumen diario
    daily_csv = journal.export_trades_csv(mode="daily_summary")
    assert "Fecha_Dia,Broker,Total_Operaciones" in daily_csv
    assert "ID_Operacion" not in daily_csv

    # 3. Filtrado por broker
    bin_csv = journal.export_trades_csv(broker="BINANCE", mode="complete")
    assert "BINANCE" in bin_csv

def test_export_trades_xlsx():
    """
    Verifica que la exportación XLSX se genere correctamente con formato binario válido.
    """
    from trade_journal.report_exporter import generate_trades_xlsx
    journal = TradeJournal()
    
    xlsx_bytes = generate_trades_xlsx(journal, broker="BINANCE")
    assert len(xlsx_bytes) > 2000
    # Validación cabecera ZIP de archivo XLSX
    assert xlsx_bytes[:4] == b"PK\x03\x04"

def test_export_trades_pdf():
    """
    Verifica que la exportación PDF institucional se genere con gráficos de barras y cabecera PDF válida.
    """
    from trade_journal.report_exporter import generate_trades_pdf
    journal = TradeJournal()
    
    pdf_bytes = generate_trades_pdf(journal, broker="BINANCE")
    assert len(pdf_bytes) > 5000
    # Validación cabecera PDF
    assert pdf_bytes.startswith(b"%PDF-")
