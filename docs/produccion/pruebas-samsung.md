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

## Live Auth0 and owner QR

- Use an Auth0 **Native** application with token-endpoint authentication set to **None** and allowed callback `mx.abarpay.mobile.qa://oidc/callback`. The Auth0 **Domain** and Native app **Client ID** identify the sign-in service and app. The Auth0 API **Identifier** is the access-token audience. These are public configuration values.
- Issue an RS256 API access token with the signed email claim `https://abarpay.app/email`. An Auth0 Post Login Action can add the claim from the test identity. If the Auth0 configuration uses a different namespaced claim, set `AUTH0_EMAIL_CLAIM` on the backend. The corresponding optional name claim is `https://abarpay.app/name`.
- Apply PostgreSQL migrations 001–003 to the isolated lab database as a separate setup step. Grant `abarpay_app` to a restricted login used by the API. Start the owner service with `ABARPAY_RUNTIME=production`, `MODO_DEMO=false`, `ABARPAY_PG_DSN`, `AUTH0_DOMAIN` and `AUTH0_AUDIENCE`. Use `SECURE_COOKIES=false` for this loopback HTTP browser test. Start it with `python -m uvicorn server.runtime:create_production_app --factory --host 127.0.0.1 --port 8011`.

Rebuild and install the same QA package with the public settings available to Gradle:

```bash
OWNER_API_BASE_URL=http://127.0.0.1:8011 \
  ./gradlew -PABARPAY_DEVICE_TEST=true \
  -PAUTH0_DOMAIN="$AUTH0_DOMAIN" \
  -PAUTH0_CLIENT_ID="$AUTH0_CLIENT_ID" \
  -PAUTH0_AUDIENCE="$AUTH0_AUDIENCE" assembleDebug
adb -d install -r app/build/outputs/apk/debug/app-debug.apk
```

On the Samsung open **Consola → Entrar a mi tienda**. Carlos signs in with the authorized test identity in the phone browser and creates a test store. On the Mac, open `http://127.0.0.1:8011/console`, start a QR challenge, and scan it from the QA app. Check that the store and matching code appear before **Aprobar acceso**. Verify the initiating browser opens the correct store and that a second browser cannot consume the approval. Add a product priced at MXN 18.00, record a cash sale with MXN 20.00 received and compare the visible folio and MXN 2.00 change against the ledger. Record approval and receipt results without capturing the QR or login callback.

## Offline cash on the physical phone

Open the POS fixture at `http://127.0.0.1:8010` in the QA app and confirm the seeded catalog and offline authorization load while connected. Use a fresh cash cart with synthetic products. Cut and restore only the POS transport:

```bash
adb -d reverse --remove tcp:8010
# Complete the cash sale on the phone, record its folio and reopen the app.
adb -d reverse --no-rebind tcp:8010 tcp:8010
```

The phone should show that it saved the cash sale locally. After reconnect, verify that the same folio, charged amount and change reached SQLite. Check that the sale has one payment and one inventory movement, including after another refresh. For a post-commit response drop, use a controlled loopback proxy at the POS boundary and record the same folio and one ledger entry across replay. A USB transport outage and a post-commit response drop are separate checks.
