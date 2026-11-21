import argparse
import importlib.machinery
import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
NOTIFIER = SCRIPTS_DIR / "notify-carlos"

_loader = importlib.machinery.SourceFileLoader("notify_carlos", str(NOTIFIER))
_spec = importlib.util.spec_from_loader("notify_carlos", _loader, origin=str(NOTIFIER))
notify = importlib.util.module_from_spec(_spec)
notify.__file__ = str(NOTIFIER)
_loader.exec_module(notify)


def write_source(tmp_path, content):
    path = tmp_path / "AskAstra.md"
    path.write_text(content, encoding="utf-8")
    return path


def make_args(**overrides):
    defaults = dict(
        question=None,
        source=None,
        state=None,
        preview=False,
        whoami=False,
        pair=False,
        resolve_sent=False,
        resolve_unsent=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def fake_keychain(service, account):
    if account == "bot-token":
        return "00000:" + "x" * 30
    if account == "chat-id":
        return "12345"
    return None


def api_response(status, payload, retry_after=None):
    return (status, json.dumps(payload).encode("utf-8"), retry_after)


REALISTIC = """### Q-001 · r1
Trabajo independiente: sí
Estado: abierta
Paquetes: M1, G2
Decisión requerida: aprobar el emisor de correo

### Q-001 · r2
Trabajo independiente: no

### Q-002 · r1
Trabajo independiente: si
"""


# --- parse ---

def test_parse_picks_latest_revision(tmp_path):
    qid, revision, can, _ = notify.read_question(write_source(tmp_path, REALISTIC), "q-001")
    assert qid == "Q-001"
    assert revision == 2
    assert can == "no"


def test_parse_normalizes_si(tmp_path):
    qid, revision, can, _ = notify.read_question(write_source(tmp_path, REALISTIC), "Q-002")
    assert can == "sí"


def test_parse_missing_question_raises(tmp_path):
    path = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    with pytest.raises(notify.NotifyError):
        notify.read_question(path, "Q-999")


def test_parse_missing_can_raises(tmp_path):
    path = write_source(tmp_path, "### Q-001 · r1\nEstado: abierta\n")
    with pytest.raises(notify.NotifyError):
        notify.read_question(path, "Q-001")


def test_parse_missing_file_raises(tmp_path):
    with pytest.raises(notify.NotifyError):
        notify.read_question(tmp_path / "nope.md", "Q-001")


def test_parse_heading_separators(tmp_path):
    for sep in ["·", "-", ".", "|"]:
        path = write_source(tmp_path, f"### Q-001 {sep} r3\nTrabajo independiente: no\n")
        _, revision, can, _ = notify.read_question(path, "Q-001")
        assert revision == 3
        assert can == "no"


def test_normalize_qid():
    assert notify.normalize_qid("q-001") == "Q-001"
    with pytest.raises(notify.NotifyError):
        notify.normalize_qid("001")
    with pytest.raises(notify.NotifyError):
        notify.normalize_qid("Q-1")


def test_build_message_is_fixed():
    message = notify.build_message("Q-001", 1, "sí")
    assert message == "Abarpay DSH\nPregunta Q-001 · r1\nTrabajo independiente: sí"


# --- state store ---

def test_state_persists_and_reloads(tmp_path):
    state_path = tmp_path / "state.json"
    store = notify.StateStore(state_path)

    def write(data):
        data["records"]["Q-001"] = {"r1": {"status": "sent", "message_id": 7}}
        store._save(data)

    store.exclusive(write)
    reloaded = json.loads(state_path.read_text(encoding="utf-8"))
    assert reloaded["records"]["Q-001"]["r1"]["status"] == "sent"


def test_state_corrupt_raises(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(notify.NotifyError):
        notify.StateStore(state_path).exclusive(lambda data: None)


# --- classification and dispatch ---

def test_send_once_classifications():
    class Client:
        def __init__(self, outcome):
            self.outcome = outcome

        def send_message(self, chat_id, text):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    ok = Client(api_response(200, {"ok": True, "result": {"message_id": 9}}))
    assert notify.send_once(ok, 1, "x") == ("sent", 9)

    malformed = Client(api_response(200, {"ok": True, "result": {}}))
    assert notify.send_once(malformed, 1, "x") == ("uncertain", None)

    rate = Client(api_response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 5}}))
    assert notify.send_once(rate, 1, "x") == ("ratelimited", 5.0)

    bad = Client(api_response(400, {"ok": False, "error_code": 400}))
    assert notify.send_once(bad, 1, "x") == ("definitive", (400, 400))

    server = Client(api_response(500, {"ok": False, "error_code": 500}))
    assert notify.send_once(server, 1, "x") == ("uncertain", None)

    transport = Client(notify.TransportNotSent())
    assert notify.send_once(transport, 1, "x") == ("transport", None)

    uncertain = Client(notify.DispatchUncertain())
    assert notify.send_once(uncertain, 1, "x") == ("uncertain", None)


def test_dispatch_success():
    class Client:
        def send_message(self, chat_id, text):
            return api_response(200, {"ok": True, "result": {"message_id": 7}})

    assert notify.dispatch(Client(), 1, "x") == ("sent", 7)


def test_dispatch_429_retries_then_success():
    class Client:
        def __init__(self):
            self.n = 0

        def send_message(self, chat_id, text):
            self.n += 1
            if self.n == 1:
                return api_response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 5}})
            return api_response(200, {"ok": True, "result": {"message_id": 8}})

    sleeps = []
    assert notify.dispatch(Client(), 1, "x", sleep_func=sleeps.append) == ("sent", 8)
    assert sleeps == [5]


def test_dispatch_429_over_cap_defers_without_early_retry():
    class Client:
        def __init__(self):
            self.calls = 0

        def send_message(self, chat_id, text):
            self.calls += 1
            return api_response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 120}})

    client = Client()
    sleeps = []
    assert notify.dispatch(client, 1, "x", sleep_func=sleeps.append) == ("deferred", 120.0)
    assert client.calls == 1
    assert sleeps == []


def test_dispatch_transport_retries_then_success():
    class Client:
        def __init__(self):
            self.attempts = 0

        def send_message(self, chat_id, text):
            self.attempts += 1
            if self.attempts < 3:
                raise notify.TransportNotSent()
            return api_response(200, {"ok": True, "result": {"message_id": 9}})

    client = Client()
    sleeps = []
    assert notify.dispatch(client, 1, "x", sleep_func=sleeps.append) == ("sent", 9)
    assert client.attempts == 3


def test_dispatch_uncertain_no_retry():
    class Client:
        def __init__(self):
            self.calls = 0

        def send_message(self, chat_id, text):
            self.calls += 1
            raise notify.DispatchUncertain()

    client = Client()
    sleeps = []
    assert notify.dispatch(client, 1, "x", sleep_func=sleeps.append) == ("uncertain", None)
    assert client.calls == 1
    assert sleeps == []


def test_request_preconnect_error_is_transport(monkeypatch):
    class Conn:
        def __init__(self, *a, **k):
            pass

        def connect(self):
            raise OSError("refused")

        def close(self):
            pass

    monkeypatch.setattr(notify.http.client, "HTTPSConnection", Conn)
    client = notify.TelegramClient("00000:" + "x" * 30)
    with pytest.raises(notify.TransportNotSent):
        client._request("POST", "/x")


def test_request_postconnect_error_is_uncertain(monkeypatch):
    class Conn:
        def __init__(self, *a, **k):
            pass

        def connect(self):
            pass

        def request(self, *a, **k):
            raise OSError("reset")

        def close(self):
            pass

    monkeypatch.setattr(notify.http.client, "HTTPSConnection", Conn)
    client = notify.TelegramClient("00000:" + "x" * 30)
    with pytest.raises(notify.DispatchUncertain):
        client._request("POST", "/x")


# --- end to end ---

def test_run_preview_no_network_no_state(tmp_path, monkeypatch, capsys):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state = tmp_path / "state.json"
    args = make_args(question="Q-001", source=str(source), state=str(state), preview=True)
    assert notify._run(args) == 0
    out = capsys.readouterr().out
    assert "Pregunta Q-001 · r1" in out
    assert "Trabajo independiente: sí" in out
    assert not state.exists()


def test_run_send_then_dedup(tmp_path, monkeypatch, capsys):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state = tmp_path / "state.json"
    monkeypatch.setattr(notify, "keychain_read", fake_keychain)

    sent = {}

    class FakeTelegramClient:
        def __init__(self, token, timeout):
            self.token = token

        def send_message(self, chat_id, text):
            sent["chat_id"] = chat_id
            sent["text"] = text
            return api_response(200, {"ok": True, "result": {"message_id": 42}})

    monkeypatch.setattr(notify, "TelegramClient", FakeTelegramClient)
    args = make_args(question="Q-001", source=str(source), state=str(state))

    assert notify._run(args) == 0
    assert sent["chat_id"] == 12345
    assert sent["text"] == "Abarpay DSH\nPregunta Q-001 · r1\nTrabajo independiente: sí"
    assert "12345" not in capsys.readouterr().out

    sent.clear()
    assert notify._run(args) == 0
    assert sent == {}
    assert "ya fue enviada" in capsys.readouterr().out


def test_run_uncertain_then_resolve_unsent(tmp_path, monkeypatch, capsys):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state = tmp_path / "state.json"
    monkeypatch.setattr(notify, "keychain_read", fake_keychain)

    class UncertainClient:
        def __init__(self, token, timeout):
            pass

        def send_message(self, chat_id, text):
            raise notify.DispatchUncertain()

    monkeypatch.setattr(notify, "TelegramClient", UncertainClient)
    args = make_args(question="Q-001", source=str(source), state=str(state))

    assert notify._run(args) == 2
    assert notify.StateStore(state).exclusive(
        lambda data: data["records"]["Q-001"]["r1"]["status"]
    ) == "uncertain"

    capsys.readouterr()
    assert notify._run(args) == 2
    assert "--resolve-sent" in capsys.readouterr().err

    resolve = make_args(question="Q-001", source=str(source), state=str(state), resolve_unsent=True)
    assert notify._run(resolve) == 0
    assert notify.StateStore(state).exclusive(
        lambda data: "Q-001" in data["records"]
    ) is False


def test_run_deferred_429_then_retry_after_elapsed(tmp_path, monkeypatch, capsys):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state = tmp_path / "state.json"
    monkeypatch.setattr(notify, "keychain_read", fake_keychain)

    class RateLimitedClient:
        def __init__(self, token, timeout):
            pass

        def send_message(self, chat_id, text):
            return api_response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 120}})

    monkeypatch.setattr(notify, "TelegramClient", RateLimitedClient)
    args = make_args(question="Q-001", source=str(source), state=str(state))

    assert notify._run(args) == 2
    record = notify.StateStore(state).exclusive(
        lambda data: data["records"]["Q-001"]["r1"]
    )
    assert record["status"] == "pending"
    assert record["retry_before"]

    capsys.readouterr()
    assert notify._run(args) == 2
    assert "en espera" in capsys.readouterr().err

    # Simulate elapsed retry window, then a successful send.
    state_path = tmp_path / "state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["records"]["Q-001"]["r1"]["retry_before"] = "2000-01-01T00:00:00Z"
    state_path.write_text(json.dumps(data), encoding="utf-8")

    sent = []

    class OkClient:
        def __init__(self, token, timeout):
            pass

        def send_message(self, chat_id, text):
            sent.append(text)
            return api_response(200, {"ok": True, "result": {"message_id": 10}})

    monkeypatch.setattr(notify, "TelegramClient", OkClient)
    assert notify._run(args) == 0
    assert len(sent) == 1


def test_run_pending_from_interruption_blocks_and_resolves(tmp_path, monkeypatch, capsys):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state_path = tmp_path / "state.json"
    store = notify.StateStore(state_path)
    store.exclusive(lambda data: data["records"].__setitem__(
        "Q-001", {"r1": {"status": "pending", "created_at": notify._utcnow(), "updated_at": notify._utcnow()}}
    ) or store._save(data))

    monkeypatch.setattr(notify, "keychain_read", fake_keychain)
    sent = []

    class Client:
        def __init__(self, token, timeout):
            pass

        def send_message(self, chat_id, text):
            sent.append(text)
            return api_response(200, {"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(notify, "TelegramClient", Client)
    args = make_args(question="Q-001", source=str(source), state=str(state_path))
    assert notify._run(args) == 2
    assert sent == []

    resolve = make_args(question="Q-001", source=str(source), state=str(state_path), resolve_unsent=True)
    assert notify._run(resolve) == 0
    assert notify.StateStore(state_path).exclusive(lambda data: "Q-001" in data["records"]) is False


def test_run_resolve_sent_marks_sent(tmp_path, monkeypatch, capsys):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state_path = tmp_path / "state.json"
    store = notify.StateStore(state_path)
    store.exclusive(lambda data: data["records"].__setitem__(
        "Q-001", {"r1": {"status": "uncertain", "created_at": notify._utcnow(), "updated_at": notify._utcnow()}}
    ) or store._save(data))

    args = make_args(question="Q-001", source=str(source), state=str(state_path), resolve_sent=True)
    assert notify._run(args) == 0
    record = notify.StateStore(state_path).exclusive(lambda data: data["records"]["Q-001"]["r1"])
    assert record["status"] == "sent"


def test_run_whoami(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(notify, "keychain_read", fake_keychain)

    class MeClient:
        def __init__(self, token, timeout):
            pass

        def get_me(self):
            return {"id": 555, "is_bot": True, "username": "abarpay_bot"}

    monkeypatch.setattr(notify, "TelegramClient", MeClient)
    assert notify._run(make_args(whoami=True)) == 0
    assert "@abarpay_bot" in capsys.readouterr().out


def test_load_chat_id_rejects_non_positive(monkeypatch):
    monkeypatch.setattr(notify, "keychain_read", lambda service, account: "-100")
    with pytest.raises(notify.NotifyError):
        notify.load_chat_id("svc", "chat-id")


def test_load_token_rejects_bad_format(monkeypatch):
    monkeypatch.setattr(notify, "keychain_read", lambda service, account: "nope")
    with pytest.raises(notify.NotifyError):
        notify.load_token("svc", "bot-token")


def test_concurrent_send_only_once(tmp_path, monkeypatch):
    source = write_source(tmp_path, "### Q-001 · r1\nTrabajo independiente: sí\n")
    state = tmp_path / "state.json"
    monkeypatch.setattr(notify, "keychain_read", fake_keychain)

    sent = []
    sent_lock = threading.Lock()

    class SlowClient:
        def __init__(self, token, timeout):
            pass

        def send_message(self, chat_id, text):
            with sent_lock:
                sent.append(text)
            time.sleep(0.05)
            return api_response(200, {"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(notify, "TelegramClient", SlowClient)
    barrier = threading.Barrier(3)
    results = []

    def worker():
        barrier.wait()
        results.append(notify._run(make_args(question="Q-001", source=str(source), state=str(state))))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    barrier.wait()
    for t in threads:
        t.join()

    assert len(sent) == 1
    assert sorted(results) == [0, 0]



def test_pair_preserves_existing_webhook():
    class ActiveWebhook:
        def read_method(self, method):
            assert method == "getWebhookInfo"
            return {"url": "https://example.invalid/hook"}

    with pytest.raises(notify.NotifyError, match="webhook activo"):
        notify.discover_destination(ActiveWebhook())


def test_pair_discloses_only_the_matching_private_chat(monkeypatch, capsys):
    monkeypatch.setattr(notify.secrets, "token_hex", lambda _: "prueba")
    monkeypatch.setattr("builtins.input", lambda: "")
    class PairClient:
        def read_method(self, method):
            if method == "getWebhookInfo":
                return {"url": ""}
            assert method == "getUpdates?limit=100&timeout=0"
            return [{"message": {"chat": {"id": chat, "type": "private"},
                                 "from": {"id": chat}, "text": text}}
                    for chat, text in [(77123, "mensaje-ajeno"), (22468, "abarpay-pair-prueba")]]
    assert notify.discover_destination(PairClient()) == 0
    out = capsys.readouterr().out
    assert "22468" in out and "77123" not in out and "mensaje-ajeno" not in out


def test_question_topics_only_use_approved_text(tmp_path):
    source = write_source(tmp_path, REALISTIC.replace("Trabajo independiente: no",
                          "Trabajo independiente: no\nTema del aviso: presupuesto\nDecisión requerida: contenido privado"))
    msg = notify.build_message(*notify.read_question(source, "Q-001"))
    assert "Aprobar presupuesto" in msg and "contenido privado" not in msg
    source.write_text(source.read_text().replace("presupuesto", "contenido privado"))
    assert "contenido privado" not in notify.build_message(*notify.read_question(source, "Q-001"))


def test_unknown_state_schema_fails_closed(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(notify.NotifyError):
        notify.StateStore(path).exclusive(lambda _: pytest.fail("estado inválido aceptado"))


def test_preview_cannot_be_combined_with_pairing():
    with pytest.raises(SystemExit):
        notify.build_parser().parse_args(["--preview", "--pair"])
