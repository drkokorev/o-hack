import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from domains.trips.providers.ostrovok import OstrovokSearchClient, OstrovokSearchError, SEARCH_URL, SearchQuery


def query(**overrides):
    data = dict(checkin=date(2027, 1, 1), checkout=date(2027, 1, 5), latitude=55.75,
                longitude=37.62, adults=2, child_ages=(6,), residency="ru")
    return SearchQuery(**(data | overrides))


def test_read_only_search_uses_official_path_and_revalidatable_prices():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "POST" and str(request.url) == SEARCH_URL
        assert json.loads(request.content)["guests"] == [{"adults": 2, "children": [6]}]
        return httpx.Response(200, json={"status": "ok", "data": {"hotels": [{"hid": 123, "id": "sample", "rates": [
            {"payment_options": {"payment_types": [{"show_amount": "100.50", "show_currency_code": "RUB"},
                                                    {"show_amount": "1.00", "show_currency_code": "USD"}]}}]}]},
            "request": {"real_ip": "192.0.2.1"}})

    client = OstrovokSearchClient("id-example", "secret-example", httpx.MockTransport(handler))
    found = client.search(query())
    assert len(seen) == 1 and found[0].hid == 123
    assert found[0].amount == Decimal("100.50") and found[0].requires_revalidation
    assert "secret-example" not in repr(client) and "192.0.2.1" not in repr(found)


@pytest.mark.parametrize("changes", [
    {"checkin": date(2027, 1, 6)}, {"latitude": 91}, {"radius": 70001},
    {"child_ages": (None,)}, {"child_ages": (18,)}, {"adults": 0}, {"adults": True}, {"radius": True},
])
def test_invalid_search_is_rejected_before_network(changes):
    def handler(request):
        raise AssertionError("network must not be called")
    client = OstrovokSearchClient("id", "secret", httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        client.search(query(**changes))


@pytest.mark.parametrize("response", [
    httpx.Response(429, text="sensitive detail"),
    httpx.Response(200, json={"status": "error", "error": "sensitive detail"}),
    httpx.Response(200, json={"status": "ok", "error": "sensitive detail", "data": {"hotels": []}}),
    httpx.Response(200, json={"status": "ok", "data": {"hotels": None}}),
])
def test_provider_failures_do_not_return_fabricated_results_or_raw_details(response):
    client = OstrovokSearchClient("id", "secret", httpx.MockTransport(lambda _: response))
    with pytest.raises(OstrovokSearchError) as error:
        client.search(query())
    assert "sensitive detail" not in str(error.value)
