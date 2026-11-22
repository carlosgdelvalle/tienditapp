package mx.abarpay.mobile

import android.util.Base64
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.security.Signature

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class OwnerQrApprovalTest {

    @Test
    fun parserReadsChallengeFields() {
        val raw = "abarpay://challenge/abc123?code=123456&nonce=N&exp=1795317555&intent=browser_login"
        val challenge = OwnerQrParser.parse(raw)
        assertEquals("abc123", challenge.id)
        assertEquals("123456", challenge.code)
        assertEquals("N", challenge.nonce)
        assertEquals("1795317555", challenge.exp)
        assertEquals("browser_login", challenge.intent)
    }

    @Test
    fun parserRejectsUnsafeChallengeId() {
        val raw = "abarpay://challenge/abc.def?code=1&nonce=N&exp=1&intent=browser_login"
        assertThrows(IllegalArgumentException::class.java) {
            OwnerQrParser.parse(raw)
        }
    }

    @Test
    fun challengePayloadMatchesServerFormat() {
        val challenge = OwnerChallenge("id", "123456", "nonce", "1795317555", "browser_login")
        val payload = OwnerQrCrypto.challengePayload(challenge, "tenant-uuid")
        val expected = listOf("id", "nonce", "1795317555", "browser_login", "tenant-uuid")
            .joinToString(10.toChar().toString())
        assertEquals(expected, payload)
    }

    @Test
    fun signAndVerifyRoundTrip() {
        val pair = OwnerQrCrypto.generateRsaKeyPair()
        val pem = OwnerQrCrypto.publicKeyPem(pair.public)
        assertTrue(pem.startsWith("-----BEGIN PUBLIC KEY-----"))

        val message = listOf("id", "nonce", "1795317555", "browser_login", "tenant-uuid")
            .joinToString(10.toChar().toString())
        val signature = OwnerQrCrypto.sign(pair.private, message)
        val verifier = Signature.getInstance("SHA256withRSA")
        verifier.initVerify(pair.public)
        verifier.update(message.toByteArray(Charsets.UTF_8))
        assertTrue(verifier.verify(Base64.decode(signature, Base64.NO_WRAP)))
    }
}
