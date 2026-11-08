#!/usr/bin/env bash
# JVM-only checks of actual domain/API source. Does not compile Compose or build an APK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${ABARPAY_TEST_CACHE:-${TMPDIR:-/tmp}/abarpay-jvm-test}"
mkdir -p "$CACHE/jars" "$CACHE/classes"
while read -r checksum path; do
  file="$CACHE/jars/$(basename "$path")"
  if [ ! -f "$file" ]; then
    curl --fail --location --silent --show-error --max-time 180 \
      "https://repo.maven.apache.org/maven2/$path" -o "$file"
  fi
  python3 - "$file" "$checksum" <<'PY'
import hashlib,sys
from pathlib import Path
actual=hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != sys.argv[2]: raise SystemExit('Dependency checksum mismatch: '+sys.argv[1])
PY
done < "$ROOT/scripts/jvm-dependencies.sha256"
CP=$(printf '%s:' "$CACHE"/jars/*.jar); CP=${CP%:}
java -cp "$CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -jvm-target 17 -classpath "$CP" -d "$CACHE/classes" \
  "$ROOT/app/src/main/java/mx/abarpay/mobile/Domain.kt" \
  "$ROOT/app/src/main/java/mx/abarpay/mobile/Repository.kt" \
  "$ROOT/app/src/test/java/mx/abarpay/mobile/DomainTest.kt" \
  "$ROOT/app/src/test/java/mx/abarpay/mobile/RepositoryTest.kt"
java -cp "$CACHE/classes:$CP" org.junit.runner.JUnitCore \
  mx.abarpay.mobile.DomainTest mx.abarpay.mobile.RepositoryTest
