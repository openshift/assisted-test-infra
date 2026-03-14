import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

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
        self._tool_calls: Dict[str, Any] = {}
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
        self._maybe_refresh_access_token()
        payload = self._build_payload(query)
        if self.streaming_enabled:
            return self._send_streaming_query(payload)
        return self._send_non_streaming_query(payload)

    def _maybe_refresh_access_token(self) -> None:
        """Refresh access token if older than threshold"""
        current_time = datetime.now()
        if self.last_auth_time is None or current_time - self.last_auth_time > timedelta(minutes=15):
            self.access_token = self._get_access_token()
            self.last_auth_time = current_time

    def _build_payload(self, query: str) -> dict:
        payload = {"query": query}
        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id
        return payload

    def _send_non_streaming_query(self, payload: dict) -> str:
        res = requests.post(
            self.assisted_chat_api_url,
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            json=payload,
            verify=False,
            timeout=60,
        )
        if res.status_code < 200 or res.status_code >= 300:
            print(f"API error {res.status_code}: {res.reason}")
            return f"API error {res.status_code}: {res.reason}"
        response_data = res.json()
        if self.conversation_id is None:
            self.conversation_id = response_data.get("conversation_id", None)
        return response_data.get("response", "")

    def _send_streaming_query(self, payload: dict) -> str:
        response_parts: list[str] = []
        # Reset tool calls collection for this request
        self._tool_calls = {}
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
                evt = self._parse_sse_line(line)
                if not evt:
                    continue
                self._accumulate_event(response_parts, evt)
        return "".join(response_parts).strip()

    def _parse_sse_line(self, line: bytes):
        """Parse a single SSE line into an event dict"""
        try:
            raw = line.decode("utf-8")
        except Exception:
            return None
        # Remove SSE prefix safely without using lstrip/rstrip with multi-char strings
        if raw.startswith("data: "):
            json_str = raw[len("data: ") :].strip()
        else:
            json_str = raw.strip()
        try:
            return json.loads(json_str)
        except Exception:
            return None

    def _accumulate_event(self, response_parts: list[str], evt: dict) -> None:
        event_name = evt.get("event")
        data = evt.get("data", {})
        if event_name == "start":
            self._update_conversation_id(data)
            return
        if event_name == "token":
            self._append_token(response_parts, data)
            return
        if event_name == "tool_result":
            self._append_tool_result(response_parts, data)
            return

    def _update_conversation_id(self, data: dict) -> None:
        if self.conversation_id is None:
            self.conversation_id = data.get("conversation_id")

    def _append_token(self, response_parts: list[str], data: dict) -> None:
        # Common shape: {"token": "..."}
        tok = data.get("token")
        if tok is None:
            tok = data.get("text") or (data.get("delta") or {}).get("content")
        if tok:
            response_parts.append(tok)

    def _append_tool_result(self, response_parts: list[str], data: dict) -> None:
        # Some streams include tool execution results with the ISO URL
        tool = data.get("token", {})
        tool_name = tool.get("tool_name")
        resp = tool.get("response")

        # Try to parse JSON payloads commonly returned by tools
        parsed_payload: Any = resp
        if isinstance(resp, str):
            try:
                parsed_payload = json.loads(resp)
            except Exception:
                parsed_payload = resp  # keep raw string if not JSON

        # Collect structured tool calls (support multiple events per tool)
        if tool_name:
            existing = self._tool_calls.get(tool_name)
            if existing is None:
                # Initialize as list of dict payloads
                self._tool_calls[tool_name] = []
                existing = self._tool_calls[tool_name]
            # Normalize: if the parsed payload is a list, extend; otherwise append single item
            if isinstance(parsed_payload, list):
                existing.extend(parsed_payload)
            else:
                existing.append(parsed_payload)

    def send_query_structured(self, query: str) -> Dict[str, Any]:
        """
        Send a query and return a structured result:
        {
          "response": str,            # aggregated text (unchanged behavior)
          "tool_calls": {             # structured tool outputs by name
              "<tool_name>": [ <parsed_payload>, ... ]
          }
        }
        """
        self._maybe_refresh_access_token()
        payload = self._build_payload(query)
        if self.streaming_enabled:
            response = self._send_streaming_query(payload)
            tool_calls = dict(self._tool_calls)
            return {"response": response, "tool_calls": tool_calls}
        response = self._send_non_streaming_query(payload)
        return {"response": response, "tool_calls": {}}

    def set_conversation_id(self, conversation_id: str):
        """Set the conversation ID to continue an existing conversation"""
        self.conversation_id = conversation_id

    def get_conversation_id(self) -> Optional[str]:
        """Get the current conversation ID"""
        return self.conversation_id
