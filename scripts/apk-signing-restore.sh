#!/usr/bin/env bash
# Restaura el keystore de firma del APK desde Keychain (iCloud).
# Uso: ./scripts/apk-signing-restore.sh  (en la Mac donde se quiera firmar)
set -euo pipefail
DEST="$HOME/.config/tienditapp"
mkdir -p "$DEST"

security find-generic-password -s abarpay-apk-signing -a keystore -w \
  | base64 --decode > "$DEST/abarpay-release.keystore"

PASS=$(security find-generic-password -s abarpay-apk-signing -a password -w)
printf 'storeFile=%s\nstorePassword=%s\nkeyAlias=abarpay\nkeyPassword=%s\n' \
  "$DEST/abarpay-release.keystore" "$PASS" "$PASS" > "$DEST/release.properties"

echo "Restaurado: $DEST/abarpay-release.keystore y release.properties"
echo "Firma: apksigner verify --print-certs android/app/build/outputs/apk/release/app-release.apk"
