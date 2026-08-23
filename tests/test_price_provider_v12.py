from investment_engine.data.providers.prices import YahooPriceProvider

def test_b3_symbol(): assert YahooPriceProvider.symbol("PETR4")=="PETR4.SA"
