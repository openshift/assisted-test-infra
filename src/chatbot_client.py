import os
from datetime import datetime, timedelta
from typing import Optional

import requests


class ChatbotClient:
    """Client for interacting with the OpenShift Assisted Chat API"""

    def __init__(self):
        self.auth_url = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        self.token = os.environ.get("OFFLINE_TOKEN")
        self.assisted_chat_api_url = os.environ.get("ASSISTED_CHAT_API_URL")
        self.conversation_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self.last_auth_time: Optional[datetime] = None

        # Validate required environment variables
        if self.token is None:
            raise ValueError("OFFLINE_TOKEN environment variable is not set")

        if self.assisted_chat_api_url is None:
            raise ValueError("ASSISTED_CHAT_API_URL environment variable is not set")

        # Initialize access token
        self.access_token = self._get_access_token()

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

        # Make request (with similar error handling as main.py)
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
