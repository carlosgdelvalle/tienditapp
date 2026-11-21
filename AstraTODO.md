# Astra TODO — Abarpay (deferred work)

> Handoff for a future agent (Astra) or Carlos on another machine.
> Each entry is self-contained: context, prerequisites, steps, and evidence criteria.

## B6 · Ergonomics acceptance — physical Android (DEFERRED)

**Status:** deferred. The build is complete (E0→D1–D3→I1–I6→M1–M7) and the B4
offline-sale core is already verified on the physical phone. B6 is the remaining
human accessibility walk.

### Context / prerequisites
- Phone: Samsung **SM-A165M**, Android **16**, SDK 36 (do NOT record its serial).
  ADB-debugging is already authorized.
- App (debug): package **mx.abarpay.mobile.dev**. Build + install:
  ```bash
  export JAVA_HOME="$HOME/.local/share/tienditapp/jdk-21/Contents/Home"
  export ANDROID_HOME="$HOME/Library/Android/sdk"
  cd android && ./gradlew assembleDebug
  adb install -r app/build/outputs/apk/debug/app-debug.apk
  ```
- Backend (demo/SIMULADO):
  ```bash
  source .venv/bin/activate
  ABARPAY_DB=server/data/abarpay.db MODO_DEMO=true OWNER_PIN=1234     ABARPAY_SYNC_SIGNING_KEY=dev-signing-key     uvicorn server.main:app --host 0.0.0.0 --port 8000
  ```
- Connectivity (dev tunnel): online = `adb reverse tcp:8000 tcp:8000`;
  offline = `adb reverse --remove tcp:8000`. The app's server URL lives in
  SharedPreferences `development_session.xml` key `server` (currently
  `http://127.0.0.1:8000`). The demo catalog is built-in, so the app also runs
  without a server (SIMULADO).

### Procedure (guide 09, scenario B6)
Record phone model + version (no serial), network state, and task. For each task
measure **tap-to-feedback** (time from tap to visible response) and
**action-to-understandable-status** (can the user tell what happened). Repeat with:
enlarged text (200%), **TalkBack**, bright lighting, and a mid-task interruption.
For the browser console use keyboard-only navigation + zoom.

| # | Task | Repeat with |
|---|---|---|
| 1 | Open app → add 2 products → **Cobrar** → **Efectivo** → read the confirmation | 200% font |
| 2 | Sell one item and read the change/status line | TalkBack |
| 3 | Repeat a sale under bright light | bright light |
| 4 | Mid-sale: lock phone, wait 10 s, reopen, finish the sale | interruption |
| 5 | Browser console `/console`: keyboard-only navigation + zoom | keyboard/zoom |

### Evidence
Record task, duration, outcome, and observed failures. Quote the exact Spanish
string the user sees/hears, or note the problem (e.g. "TalkBack reads the amount
as a raw number, not 'veintidós pesos'"). Distinguish physical-device vs
second-client. Screenshots: `adb exec-out screencap -p > /tmp/abarpay-shots/<n>.png`.
No hard pass/fail threshold — the deliverable is the written observation report
so the team can prioritize fixes.

## B4 · remaining physical sub-scenarios (optional, unit-covered)
Not yet re-walked on the phone (covered by server unit tests): last-unit conflict
across two tills, force-close/reboot + reconnect, lost-ACK retry. The core offline
loop (offline → local finalize → reconnect → exactly-once sync) is already verified
(bítacora `2026-11-21-1455-b4-venta-offline.md`).

## Cleanup (when testing is done)
- Remove the temporary diagnostic log `android.util.Log.e("abarpay", ...)` in
  `ShopViewModel.kt` (commit `07fe3a2`).
