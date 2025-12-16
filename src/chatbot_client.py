import json
import os
from datetime import datetime, timedelta
from typing import Optional

import requests


class ChatbotClient:
    """Client for interacting with the OpenShift Assisted Chat API"""

    def __init__(self, streaming_enabled: Optional[bool] = None):
        self.auth_url = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        self.token = os.environ.get("OFFLINE_TOKEN")
        self.assisted_chat_api_url = os.environ.get("ASSISTED_CHAT_API_URL")
        self.conversation_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self.last_auth_time: Optional[datetime] = None
        # Determine streaming mode:
        # 1) explicit arg overrides env
        # 2) env overrides default
        # 3) default = True
        env_val = os.environ.get("CHATBOT_STREAMING_ENABLED")
        if streaming_enabled is not None:
            self.streaming_enabled = bool(streaming_enabled)
        elif env_val is not None:
            self.streaming_enabled = env_val.lower() in ("1", "true", "yes", "on")
        else:
            self.streaming_enabled = True

        # Validate required environment variables
        if self.token is None:
            raise ValueError("OFFLINE_TOKEN environment variable is not set")

        if self.assisted_chat_api_url is None:
            raise ValueError("ASSISTED_CHAT_API_URL environment variable is not set")

        # Resolve endpoint: support base '/v1' or full paths ending with '/query' or '/streaming_query'
        self.assisted_chat_api_url = self._resolve_endpoint(self.assisted_chat_api_url, self.streaming_enabled)

        # Initialize access token
        self.access_token = self._get_access_token()

    @staticmethod
    def _resolve_endpoint(base_or_full: str, streaming_enabled: bool) -> str:
        """
        Accept either a full endpoint ending with '/query' or '/streaming_query',
        or a base URL (e.g., 'https://assisted-chat.api.openshift.com/v1') and append the proper suffix.
        """
        s = base_or_full.rstrip("/")
        if s.endswith("/query") or s.endswith("/streaming_query"):
            return s
        # Treat URLs ending with '/v1' (or similar version path) as base
        if s.endswith("/v1"):
            return s + ("/streaming_query" if streaming_enabled else "/query")
        # Fallback: append appropriate path
        return s + ("/streaming_query" if streaming_enabled else "/query")

    def _get_access_token(self) -> str:
        """Get access token using refresh token"""
        res = requests.post(
            self.auth_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.token,
                "client_id": "cloud-services",
            },
            verify=False,
        )

        if res.status_code >= 400 and res.status_code < 500:
            raise Exception(f"Got authentication error - {res.status_code}: {res.reason}")

        token = res.json()["access_token"]
        self.last_auth_time = datetime.now()
        return token

    def send_query(self, query: str) -> str:
        """Send a query to the chatbot and return the response"""
        # Prepare request payload (refresh token if too old)
        current_time = datetime.now()
        if self.last_auth_time is None or current_time - self.last_auth_time > timedelta(minutes=15):
            self.access_token = self._get_access_token()
            self.last_auth_time = current_time

        payload = {"query": query}

        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id

        # Streaming endpoint support (driven by streaming_enabled flag)
        if self.streaming_enabled:
            response_parts: list[str] = []
            with requests.post(
                self.assisted_chat_api_url,
                headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
                json=payload,
                stream=True,
                verify=False,
                timeout=60,
            ) as byte_resp:
                if byte_resp.status_code < 200 or byte_resp.status_code >= 300:
                    return f"API error {byte_resp.status_code}: {byte_resp.reason}"

                for line in byte_resp.iter_lines():
                    if not line:
                        continue
                    raw = line.decode("utf-8")
                    # Remove SSE prefix safely without using lstrip/rstrip with multi-char strings
                    if raw.startswith("data: "):
                        json_str = raw[len("data: ") :].strip()
                    else:
                        json_str = raw.strip()
                    try:
                        evt = json.loads(json_str)
                    except Exception:
                        continue
                    event_name = evt.get("event")
                    data = evt.get("data", {})
                    if event_name == "start" and self.conversation_id is None:
                        self.conversation_id = data.get("conversation_id")
                    elif event_name == "token":
                        # Common shape: {"token": "..."}
                        tok = data.get("token")
                        if tok is None:
                            tok = data.get("text") or (data.get("delta") or {}).get("content")
                        if tok:
                            response_parts.append(tok)
            return "".join(response_parts).strip()

        # Non-streaming JSON endpoint
        res = requests.post(
            self.assisted_chat_api_url,
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            json=payload,
            verify=False,
            timeout=60,
        )

        if res.status_code < 200 or res.status_code >= 300:
            # Log the error but don't raise exception (like main.py)
            print(f"API error {res.status_code}: {res.reason}")
            return f"API error {res.status_code}: {res.reason}"

        response_data = res.json()

        # Handle new conversation
        if self.conversation_id is None:
            self.conversation_id = response_data.get("conversation_id", None)

        return response_data.get("response", "")

    def set_conversation_id(self, conversation_id: str):
        """Set the conversation ID to continue an existing conversation"""
        self.conversation_id = conversation_id

    def get_conversation_id(self) -> Optional[str]:
        """Get the current conversation ID"""
        return self.conversation_id
