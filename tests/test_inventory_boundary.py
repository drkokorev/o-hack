import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from domains.trips import offers
from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
from domains.trips.providers.demo_config import load_demo_config
from domains.trips.providers.demo_inventory import DemoInventory


def test_snapshot_identity_does_not_make_price_or_reviews_real():
    provider = DemoInventory(catalog=lambda: {'hotels': {'sochi': [
        {'id': 'fixture-1', 'name': 'Тестовый объект', 'kind': 'hotel', 'lat':43.58,'lon':39.72}]}})
    hotel = provider.hotels_for('sochi')[0]
    assert hotel.source == 'overture'
    assert hotel.field_sources() == {'identity':'overture', 'price':'demo', 'rating':'demo',
        'reviews':'demo', 'amenities':'unverified_demo','cancellation':'demo','availability':'not_checked'}


def test_inventory_port_can_replace_transport_without_changing_planning_code(monkeypatch):
    class NoRoutes:
        def transport_options(self, origin, dest, day, mode=None):
            return []
    monkeypatch.setattr(offers, 'inventory', NoRoutes())
    assert offers.transport_options(ORIGIN_BY_NAME['Москва'], BY_ID['sochi'], date(2026,12,5)) == []


def test_demo_config_cannot_claim_to_be_live(tmp_path):
    source = Path(__file__).parents[1] / 'domains/trips/data/demo_inventory.json'
    values = json.loads(source.read_text(encoding='utf-8'))
    values['source'] = 'live'
    target = tmp_path / 'bad.json'
    target.write_text(json.dumps(values), encoding='utf-8')
    with pytest.raises(ValidationError):
        load_demo_config(target)


def test_same_snapshot_and_query_produce_same_demo_offers():
    provider = DemoInventory(catalog=lambda: {})
    assert provider.hotels_for('kazan') == provider.hotels_for('kazan')


def test_a_replaced_provider_cannot_reuse_the_previous_providers_cache(monkeypatch):
    class Provider:
        def __init__(self, value):
            self.value = value
        def hotels_for(self, dest_id, count=12):
            return self.value
    monkeypatch.setattr(offers, 'inventory', Provider(('first',)))
    assert offers.hotels_for('kazan') == ('first',)
    monkeypatch.setattr(offers, 'inventory', Provider(('second',)))
    assert offers.hotels_for('kazan') == ('second',)
