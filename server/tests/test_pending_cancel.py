"""Unpaid-only cancellation uses FakePey SIMULADO, never real money."""

import pytest

from server.tests.conftest import create_pey_sale, event_payload, post_webhook

pytestmark = pytest.mark.usefixtures("staff")


def test_pending_cancel_is_idempotent_and_late_payment_is_not_applied(client, db):
    sale = create_pey_sale(client)
    url = f"/api/sales/{sale['id']}/cancel?pendingOnly=true"
    assert client.post(url).json()['status'] == 'canceled'
    assert client.post(url).json()['status'] == 'canceled'
    assert db.execute('SELECT stock_milli FROM products WHERE id=1').fetchone()[0] == 24000
    event = event_payload(sale['qrId'], 'SIMULADO-late-cancel')
    assert post_webhook(client, event, 'SIMULADO-cancel-event').status_code == 200
    assert client.get(f"/api/sales/{sale['id']}").json()['status'] == 'canceled'
    assert db.execute('SELECT applied FROM payments WHERE sale_id=?', (sale['id'],)).fetchone()[0] == 0
    assert db.execute('SELECT stock_milli FROM products WHERE id=1').fetchone()[0] == 24000


def test_payment_found_during_cancel_is_preserved(client, fake_pey, db):
    sale = create_pey_sale(client)
    fake_pey.add_transaction(sale['qrId'], 'SIMULADO-before-cancel', 0.01)
    response = client.post(f"/api/sales/{sale['id']}/cancel?pendingOnly=true")
    assert response.status_code == 409
    assert client.get(f"/api/sales/{sale['id']}").json()['status'] == 'paid_pey'
    assert db.execute('SELECT stock_milli FROM products WHERE id=1').fetchone()[0] == 23000
    assert db.execute("SELECT COUNT(*) FROM inventory_movements WHERE reason='cancel'").fetchone()[0] == 0
