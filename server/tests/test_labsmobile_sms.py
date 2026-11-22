import httpx
import pytest

from server.owner_phone import LABSMOBILE_SEND_URL, PhoneSettings


LAB_ENV = {
    "ABARPAY_OWNER_SMS_PROVIDER": "labsmobile",
    "ABARPAY_OWNER_CODE_KEY": "qa" * 16,
    "ABARPAY_LABSMOBILE_USERNAME": "qa",
    "ABARPAY_LABSMOBILE_TOKEN": "simulated",
}


@pytest.mark.parametrize("prefix", ["52", "521"])
def test_labsmobile_sends_abar_pay_code_on_the_confirmed_route(monkeypatch, prefix):
    def simulated_post(url, *, json, auth, timeout, follow_redirects):
        assert url == LABSMOBILE_SEND_URL
        assert json == {
            "recipient": [{"msisdn": prefix + "4421234567"}],
            "message": "Abarpay: tu código es 123456. No lo compartas.",
        }
        assert auth == ("qa", "simulated")
        assert timeout == 5
        assert not follow_redirects
        return httpx.Response(200, json={"code": "0", "subid": "simulado"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", simulated_post)
    PhoneSettings.from_env({**LAB_ENV, "ABARPAY_LABSMOBILE_MX_PREFIX": prefix}).send("+524421234567", "123456")


def test_labsmobile_rejects_provider_error_even_with_http_200(monkeypatch):
    monkeypatch.setattr(
        httpx, "post",
        lambda url, **_: httpx.Response(200, json={"code": "35"}, request=httpx.Request("POST", url)),
    )
    settings = PhoneSettings.from_env({**LAB_ENV, "ABARPAY_LABSMOBILE_MX_PREFIX": "52"})
    with pytest.raises(RuntimeError, match="did not accept"):
        settings.send("+524421234567", "123456")


def test_labsmobile_fails_closed_without_confirmed_prefix():
    with pytest.raises(RuntimeError, match="confirmed Mexico prefix"):
        PhoneSettings.from_env(LAB_ENV)
