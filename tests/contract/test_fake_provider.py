"""The in-memory fake passes the MarketDataProvider contract (task 1.9)."""

import pytest
from fakes.fake_market_data import FakeMarketData

from contract.market_data_contract import MarketDataProviderContract, ProviderFactory


class TestFakeMarketDataProvider(MarketDataProviderContract):
    @pytest.fixture
    def make_provider(self) -> ProviderFactory:
        return FakeMarketData
