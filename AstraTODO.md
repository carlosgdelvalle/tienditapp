# Astra TODO · Abarpay recovery and acceptance

Baseline `355db73`. Use the candidate SHA from the integration run for acceptance. The [recorded device run](docs/bitacora/2026-11-21-1455-b4-venta-offline.md) covers one offline cash sale using an ADB reverse tunnel. The current work follows the [full acceptance scenarios](docs/produccion/09-paquetes-y-aceptacion.md#acceptance-scenarios-and-evidence).

## B3 and B4 · Payment and offline regressions

The [automated acceptance tests](server/tests/test_payment_offline_acceptance.py) use a temporary database and FakePey SIMULADO. From the repo root with the server test environment activated, run:

```bash
python -m pytest -q server/tests/test_payment_offline_acceptance.py server/tests/test_checkout_till.py
```

With JDK 21 and the Android SDK configured, run `./gradlew testDebugUnitTest --tests mx.abarpay.mobile.SaleCoordinatorTest` from `android/`. The MockWebServer case drops the sync connection after receiving the event and checks that reopening the outbox resends the same event before accepting the duplicate acknowledgment.

| Scenario | Acceptance evidence |
| --- | --- |
| Confirmed CoDi after another till sells the last unit | Signed webhook and provider readback each persist the confirmed payment. Repeat delivery leaves one payment for the transaction. Inventory shortage has a traceable variance. |
| Catalog price changes before offline replay | The sale, receipt, change, and payment preserve the amount derived from the server-issued catalog at checkout. A repeated event returns the same receipt with one stock movement. |
| Online checkout commits before the response is lost | The same operation reaches the offline journal and replays after reconnect. Both paths resolve to one sale ID and one set of ledger and inventory entries. |
| Two tills sell the last unit while disconnected | Both cash sales reach the ledger. The shortage has an auditable variance linked to the affected sale and product. Replaying either sale leaves the ledger and stock evidence unchanged. |
| Phone restarts with a cash sale and a goods receipt pending | Start from a cached order and catalog on the physical phone. Record synthetic operations in airplane mode, force-stop, reboot, and reconnect. Check the local receipts, stable references, server ledger, and pending discrepancy. Confirm the same stock receipt is published once after approval. |

Run the physical B4 cases against an isolated backend with a second till. Measure checkout through reconnect and record the pending status before sync. Use a controlled response drop after commit on the isolated test network for the lost-response case. Compare the reference, amount, change, and inventory evidence before and after replay. The API tests and the single-sale phone run exercise distinct parts of this sequence.

## B6 · Ergonomics

Astra can review keyboard and zoom behavior and prepare the device script. Carlos or a test cashier operates the Samsung SM-A165M (Android 16) for TalkBack and bright-light observations. A demo-device pass can establish a checkout baseline. Run final acceptance against the integrated app and consoles.

Use synthetic data in an isolated test store and record the APK SHA, source revision, device model and Android version, network state, task, time from tap to visible feedback, time to a status the operator understands, exact Spanish copy, and PASS/FAIL/BLOCKED with sanitized evidence. Omit the device serial.

| Task | Acceptance evidence |
| --- | --- |
| Add two products and take cash at 200% text | The total, confirmation, and change remain visible and usable. |
| Complete checkout with TalkBack | Controls announce their purpose and state. Product, quantity, total, method, and result arrive in a logical order. |
| Repeat a sale in bright light | The amount, action, and result are legible. Text or icons convey state alongside color. |
| Lock and reopen mid-sale, then repeat on a slow connection | The cart and current step survive. The wait state is visible and the operator can tell if the sale is pending, saved locally, or confirmed. |
| Sign in and open a sales view in the browser with keyboard and zoom | Focus is visible and logical. Dialogs return focus. The primary actions stay reachable. |

Use the [design criteria and timing guidance](docs/produccion/03-flujos-y-ergonomia.md#physical-android-acceptance-protocol) to classify failures. Pair proposed workflow changes with their developer before implementation.

## B8 · Recoverable release

Verify the signed APK against the candidate's Digital Asset Links certificate. Upgrade in place with a pending outbox. Verify recovery and one replay, restore a backup into a separate database, and rehearse rollback to a compatible build. Record both SHAs and the observed recovery times. See [release acceptance](docs/produccion/09-paquetes-y-aceptacion.md#acceptance-scenarios-and-evidence).
