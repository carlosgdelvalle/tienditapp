# Samsung integration test

Run this lab on the Mac that has the Samsung connected by USB. Use the integration branch `cdv/integracion-dueno-caja`, an isolated PostgreSQL database and a separate SQLite POS fixture. Record the source SHA, device model, Android version and result. Omit the device serial and sign-in material.

## Build and connect

```bash
cd android
./gradlew -PABARPAY_DEVICE_TEST=true assembleDebug
adb -d install -r app/build/outputs/apk/debug/app-debug.apk
adb -d reverse --no-rebind tcp:8010 tcp:8010
adb -d reverse --no-rebind tcp:8011 tcp:8011
```

The phone launcher calls the app **Abarpay QA** and its package is `mx.abarpay.mobile.qa`. Use port 8010 for the SQLite cash fixture and port 8011 for the PostgreSQL owner API. Both services listen on Mac loopback. Android reaches them over USB using the same `127.0.0.1` addresses. The QA package has its own app data and Android Keystore.

## Owner phone sign-in and QR

1. Apply migrations 001–004 to the isolated PostgreSQL lab as the migrator. Grant `abarpay_app` to a restricted login for the API. Run `server.runtime:create_production_app` on Mac loopback port 8011 with `ABARPAY_RUNTIME=production`, `MODO_DEMO=false`, and `ABARPAY_PG_DSN`. For this HTTP lab only, set `SECURE_COOKIES=false`. Inject a `PhoneSettings` sender that captures generated codes in a private, in-memory test inbox. Use a synthetic Mexican number and enter the code on the Samsung. Keep the inbox out of HTTP routes, logs and source control.
2. Configure the QA APK with the loopback owner API and install it over the existing QA package.

   ```bash
   cd android
   ./gradlew -PABARPAY_DEVICE_TEST=true -POWNER_API_BASE_URL=http://127.0.0.1:8011 assembleDebug
   adb -d install -r app/build/outputs/apk/debug/app-debug.apk
   ```

3. Open **Consola → Entrar a mi tienda**, enter the number and test SMS code, and create a synthetic store. Close and reopen the app. Confirm it reaches **Escanear código QR** without another message.
4. On the Mac, open `http://127.0.0.1:8011/console`, select **Mostrar código QR**, and scan it with the Samsung. Compare the code and store before selecting **Sí, abrir la consola**. Check that the same browser opens the correct store. A separate browser and a repeated exchange must be refused.
5. Add a product priced at MXN 18.00 in the console. Record a cash sale with MXN 20.00 received. Match the receipt reference, MXN 2.00 change and the single sale against PostgreSQL.

Label the SMS and store fixtures **SIMULADO** in the test record. Record physical camera approval and real carrier delivery separately. Repeat the message check with an authorized Mexican SIM and an approved transport before the pilot. See the [LabsMobile setup and simulated SMS notes](labsmobile-sms.md).

## Connected cash and the QR console

Use the same isolated PostgreSQL backend for the QR console and **Caja** in Abarpay QA. Open **Catálogo** in the browser, add a fixture item, then edit its name and price. Check that Caja loads the edited product and that editing leaves the stock unchanged.

Record one cash sale in **Caja → Entrar a mi tienda**. To test loss of a response, wrap the QA server so the first successful mobile checkout response becomes an error after the database commit. Restart the Android app and select **Consultar venta pendiente**. Compare the full folio and total with **Historial de ventas** and verify one sale, payment, and stock movement for that folio in PostgreSQL. Check **Inicio** for the current business day's count and amount. In a separate browser, use a second verified owner with a different store. The sale must be absent from their history and return HTTP 404 when requested directly.

The connected owner checkout and the SQLite offline POS fixture use separate routes.

## Inventory between the console and Samsung

In the QR console, open **Inventario**, choose a finite-stock fixture product, and save a physical count with a reason. Verify the new count and one adjustment in **Movimientos recientes**. Open **Caja** on the Samsung or select **Actualizar catálogo** with an empty cart. Confirm the phone shows the same count. Sell one unit and refresh **Inventario** in the console. Verify both show one fewer unit and the console shows the sale movement.

From a different owner's QR session, confirm that the product and movements are absent and that the adjustment endpoint returns HTTP 404 for the first store's product. To check stale counts, open an adjustment and change the same stock from a second authorized request. The stale save must return 409. Refresh inventory and confirm the old editor closes so the owner starts from the latest count.

## Employee invitation and phone enrollment

Use the isolated PostgreSQL lab with the employee phone migration applied and the private simulated SMS sender. Install a separate employee QA build. The owner QA package and the employee QA package each have a separate signing key in Android Keystore.

```bash
cd android
./gradlew -PABARPAY_DEVICE_TEST=true -PABARPAY_DEVICE_TEST_ROLE=employee \
  -POWNER_API_BASE_URL=http://127.0.0.1:8011 assembleDebug
adb -d install -r app/build/outputs/apk/debug/app-debug.apk
```

1. In the owner QR console, open **Equipo**, enter a synthetic Mexican number, grant **Puede cobrar**, and create the invitation. Open the link in the employee QA build (`mx.abarpay.mobile.qa.equipo`). Keep the link and code private.
2. Review the store and grants, enter a fictional name, and request the simulated code for the invited number. Enter it in Abarpay QA Equipo. Verify that **Mi turno** shows only **Cobrar en efectivo** and that the new employee appears in the owner's Team list.
3. Record a fixture cash sale. Verify that the sale is attributed to the employee and appears in the store history. Replace the cash grant with **Puede ajustar inventario** from the owner console, then refresh the employee's access. Confirm only **Inventario** is shown and record a fixture adjustment.
4. Replace the inventory grant with **Puede fiar** and check that only **Fiado** is offered. Record a fixture movement. Suspend employee access, refresh and reopen the app, and verify that the employee cannot enter a store. The backend must reject denied operations even if a client calls an endpoint directly.

## Offline cash on the physical phone

### PostgreSQL and phone sign-in

1. Apply migration `006_offline_cash.sql` to a disposable PostgreSQL QA database, start the phone-enabled runtime and open **Caja** on the Samsung. A store owner or employee with **Puede cobrar** can prepare the till. Wait for the catalog and **Trabajar sin conexión**. Keep the owner QR console open in Chrome.
2. Enable airplane mode, turn off Wi-Fi, and remove the USB reverse tunnel for the phone API. Start a fresh cash sale in **Caja**. Record the folio, total, change, and **Venta guardada en este celular** message. Confirm the folio is absent from PostgreSQL at this point.
3. Force-stop and reopen Abarpay with the phone still offline. Open **Caja** or the employee's **Cobrar en efectivo**. Check the same receipt and pending count. Change the fixture product's price in the QR console while the phone stays disconnected.
4. Restore the connection and tunnel. Reopen **Caja** if needed and wait for synchronization. Check the same folio and amounts on the phone and in **Historial de ventas**, with one payment and one inventory movement in PostgreSQL. The recorded price stays the one shown at checkout.
5. With two independently enrolled tills, prepare them with one available piece. Keep both offline as they sell that piece, then reconnect. Check both sales and the **Faltante por venta sin conexión** movement tied to the sale that applied second. The isolated PostgreSQL acceptance test covers this case with two authenticated devices and concurrent replay.

### SQLite demo

Open the POS fixture at `http://127.0.0.1:8010` in the QA app and confirm the seeded catalog and offline authorization load while connected. Use a fresh cash cart with synthetic products. Cut and restore only the POS transport:

```bash
adb -d reverse --remove tcp:8010
# Complete the cash sale on the phone, record its folio and reopen the app.
adb -d reverse --no-rebind tcp:8010 tcp:8010
```

The phone should show that it saved the cash sale locally. After reconnect, verify that the same folio, charged amount and change reached SQLite. Check that the sale has one payment and one inventory movement, including after another refresh. For a post-commit response drop, use a controlled loopback proxy at the POS boundary and record the same folio and one ledger entry across replay. A USB transport outage and a post-commit response drop are separate checks.
