import pyotp
import requests
import upstox_client
from urllib.parse import urlparse, parse_qs
import logging

class UpstoxAuth:
    """
    Handles secure Upstox API authentication.
    Uses API Key, API Secret, and a TOTP secret via pyotp to generate
    a fresh access token without manual login.
    """
    def __init__(self, api_key: str, api_secret: str, redirect_uri: str, totp_secret: str, mobile_number: str, pin: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self.totp_secret = totp_secret
        self.mobile_number = mobile_number
        self.pin = pin
        self.access_token = None
        self.session = requests.Session()
        self.base_url = "https://api.upstox.com/v2"

    def generate_totp(self) -> str:
        """Generates the current TOTP using pyotp."""
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()

    def get_access_token(self) -> str:
        """
        Automates the login flow to get an access token.
        """
        try:
            code = self._automated_login_flow()

            url = f"{self.base_url}/login/authorization/token"
            headers = {
                'accept': 'application/json',
                'Api-Version': '2.0',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            data = {
                'code': code,
                'client_id': self.api_key,
                'client_secret': self.api_secret,
                'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code'
            }

            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()

            json_response = response.json()
            self.access_token = json_response.get('access_token')
            return self.access_token

        except Exception as e:
            logging.error(f"Failed to get access token: {e}")
            raise

    def _automated_login_flow(self) -> str:
        """
        Executes the login steps using mobile, PIN and TOTP to retrieve the authorization code.
        Note: This simulates the Upstox OAuth login flow using their internal APIs.
        """
        headers = {
            'accept': 'application/json',
            'Api-Version': '2.0',
            'Content-Type': 'application/json'
        }

        # Step 1: Initialize Authorize and get redirect url
        auth_url = f"{self.base_url}/login/authorization/dialog"
        params = {
            "response_type": "code",
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri
        }
        res = self.session.get(auth_url, params=params, allow_redirects=True)
        # Parse user_id from the redirect URL
        parsed = urlparse(res.url)
        qs = parse_qs(parsed.query)
        user_id = qs.get("user_id", [None])[0]
        if not user_id:
            raise Exception("Failed to get user_id from authorization dialog")

        # Step 2: Generate OTP
        generate_otp_url = "https://api.upstox.com/v2/login/open/v6/auth/1fa/otp/generate"
        otp_payload = {
            "data": {
                "mobileNumber": self.mobile_number,
                "userId": user_id
            }
        }
        res = self.session.post(generate_otp_url, headers=headers, json=otp_payload)
        res.raise_for_status()
        validate_otp_token = res.json().get('data', {}).get('validateOTPToken')

        # Step 3: Verify TOTP
        verify_totp_url = "https://api.upstox.com/v2/login/open/v4/auth/1fa/otp-totp/verify"
        totp_payload = {
            "data": {
                "otp": self.generate_totp(),
                "validateOtpToken": validate_otp_token
            }
        }
        res = self.session.post(verify_totp_url, headers=headers, json=totp_payload)
        res.raise_for_status()

        # Step 4: Submit PIN (2FA)
        import base64
        pin_encoded = base64.b64encode(self.pin.encode()).decode()
        submit_pin_url = "https://api.upstox.com/v2/login/open/v3/auth/2fa"
        pin_payload = {
            "data": {
                "twoFAMethod": "SECRET_PIN",
                "inputText": pin_encoded
            }
        }
        res = self.session.post(
            submit_pin_url,
            headers=headers,
            json=pin_payload,
            params={"client_id": self.api_key, "redirect_uri": self.redirect_uri},
            allow_redirects=True
        )
        res.raise_for_status()

        # Step 5: OAuth Authorization
        oauth_auth_url = "https://api.upstox.com/v2/login/v2/oauth/authorize"
        oauth_payload = {
            "data": {
                "userOAuthApproval": True
            }
        }
        res = self.session.post(
            oauth_auth_url,
            headers=headers,
            json=oauth_payload,
            params={"client_id": self.api_key, "redirect_uri": self.redirect_uri, "response_type": "code"},
            allow_redirects=True
        )
        res.raise_for_status()

        # Extract code from final redirect uri
        redirect_uri = res.json().get('data', {}).get('redirectUri')
        if not redirect_uri:
            raise Exception("Failed to get redirectUri after oauth authorization")

        parsed = urlparse(redirect_uri)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        if not code:
            raise Exception("Failed to extract authorization code")

        return code

    def get_api_client(self):
        """Returns the Upstox API client authenticated with the access token."""
        if not self.access_token:
            self.get_access_token()

        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token
        return upstox_client.ApiClient(configuration)
