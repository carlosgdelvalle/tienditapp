# LabsMobile for Abarpay owner sign-in

## Pilot recommendation

LabsMobile is the first provider to try for delivering Abarpay's owner verification codes in Mexico. Abarpay generates and validates the codes, pairs the Android device, and issues sessions. LabsMobile delivers the message.

Public terms checked November 21, 2026. LabsMobile advertises Mexico SMS from **MXN 0.224 per message**, a minimum paid top-up of **US$10 or €9**, and no setup or maintenance fee. It offers welcome credits after account validation. The Mexico page lists Telcel, AT&T, Movistar, and several virtual operators. It offers a priority route for verification traffic on request. Confirm whether welcome credits cover that route, its unit price and any fees, and coverage for Altán-based lines. Delivery claims still need handset evidence. [Mexico coverage and pricing](https://www.labsmobile.com/es/plataforma-envio-sms-masivo/mexico) · [Welcome credit process](https://www.labsmobile.com/es/blog/api-envios-sms)

## Set up a live test

1. Put an active Mexican SIM that you control in the Samsung and confirm it can receive an ordinary text. Use the same Samsung and the local Abarpay QA setup. [Samsung runbook](pruebas-samsung.md)
2. Register and verify a LabsMobile account. Request welcome credits and the Mexico priority route for sending an Abarpay-generated verification code. Ask support whether its API expects `52` plus ten digits on that route or the legacy `521` in its Mexico examples. Keep standard `+52` phone numbers in Abarpay. Format the destination at the provider boundary according to the confirmed route. [Account registration](https://www.labsmobile.com/es/registro) · [Mexico coverage and sender options](https://www.labsmobile.com/es/plataforma-envio-sms-masivo/mexico) · [Mexican numbering](https://www.ift.org.mx/sites/default/files/las_10_de_marcacion_a_10_v5.pdf)
3. Generate a dedicated QA API token. Save it in Keychain on the Mac running the test. Supply the variables below to the isolated PostgreSQL QA process. The adapter uses HTTP Basic authentication and treats a nonzero provider code as a send failure, even when the provider replies with HTTP 200. [LabsMobile REST API](https://www.labsmobile.com/en/sms-api/api-versions/http-rest-post-json) · [Adapter](../../server/owner_phone.py)
4. With the QA adapter and a fresh isolated lab database, run the Samsung enrollment. Confirm that the app requests a code, the SMS reaches Android Messages, and entering the code pairs the device. Restart the app to verify sign-in with the paired key, then scan and approve the console QR. Repeat for an employee invited in Equipo. With one SIM, use a separate QA database with a previously enrolled synthetic owner for the employee run. Record the carrier, elapsed time, resend count, and outcome. Repeat on Telcel, AT&T, Movistar, and an Altán-based line before choosing the production route.

| Variable | QA value |
| --- | --- |
| `ABARPAY_OWNER_SMS_PROVIDER` | `labsmobile` |
| `ABARPAY_OWNER_CODE_KEY` | Separate random value of at least 32 bytes |
| `ABARPAY_LABSMOBILE_USERNAME` | Verified LabsMobile account username |
| `ABARPAY_LABSMOBILE_TOKEN` | Dedicated QA API token from Keychain |
| `ABARPAY_LABSMOBILE_MX_PREFIX` | `52` or `521`, as confirmed for the account's Mexico route |

## Run now with simulated SMS

Abarpay already supports this in the local QA lab. Open **Consola → Entrar a mi tienda** in **Abarpay QA** and enroll with a synthetic Mexican number in a fresh lab database. The same backend code generates an expiring, single-use code and passes it to the injected `PhoneSettings` sender. The local sender puts it in a private in-memory inbox. The Mac reads it over a private Unix socket and uses USB debugging to enter it in the Samsung's normal code field. Android Messages stays empty because no carrier is involved.

This exercises the real backend verification and device binding, including the normal QR flow. The lab inbox belongs on the test Mac and stays out of API responses, logs, and production configuration. A phone already paired to the current lab will sign in with its key, so use a fresh isolated database to repeat first enrollment while preserving the phone's existing app data.

The same enrollment and QR checks can be run without the phone using the PostgreSQL integration test. Run with PostgreSQL's `initdb` and `pg_ctl` on `PATH` so the test can start its temporary cluster.

```bash
python -m pytest -q server/tests/test_runtime_pg.py -k owner_phone_enrollment_and_qr_without_oidc
```

See the [physical Samsung test record](../bitacora/2026-11-21-2330-dueno-acceso-celular.md) for the completed simulated run.
