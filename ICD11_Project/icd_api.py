import argparse
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"


class ICDError(Exception):
    pass


def read_response(response, operation):
    if not response.ok:
        hints = {
            400: "Check the request or OAuth settings.",
            401: "Check your WHO credentials.",
            403: "Check your WHO API access.",
            404: "Check the ICD-11 release.",
            429: "Rate limit reached. Try again later.",
        }
        hint = hints.get(response.status_code, "Check WHO API availability.")
        raise ICDError(f"{operation} failed (HTTP {response.status_code}). {hint}")

    try:
        data = response.json()
    except ValueError:
        raise ICDError(f"{operation} returned invalid JSON.") from None

    if not isinstance(data, dict):
        raise ICDError(f"{operation} returned an unexpected response.")

    return data


class ICDClient:
    def __init__(self):
        load_dotenv(Path(__file__).with_name(".env"))

        self.client_id = os.getenv("WHO_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("WHO_CLIENT_SECRET", "").strip()
        self.release = os.getenv("WHO_ICD_RELEASE", "2026-01").strip()
        self.language = os.getenv("WHO_ICD_LANGUAGE", "en")
        self.tm2_subtree = os.getenv("WHO_TM2_SUBTREE", "").strip()

        if not self.client_id or not self.client_secret:
            raise ICDError("Fill in WHO_CLIENT_ID and WHO_CLIENT_SECRET in .env.")

        if not re.fullmatch(r"\d{4}-\d{2}", self.release):
            raise ICDError("WHO_ICD_RELEASE must use YYYY-MM format.")

        self.session = requests.Session()
        self.token = ""
        self.token_expires_at = 0

    def request(self, method, url, **kwargs):
        try:
            return self.session.request(
                method, url, timeout=(5, 20), allow_redirects=False, **kwargs
            )
        except requests.Timeout:
            raise ICDError("WHO request timed out. Try again.") from None
        except requests.RequestException:
            raise ICDError("Could not connect to WHO. Check your internet.") from None

    def get_token(self):
        if self.token and time.monotonic() < self.token_expires_at:
            return self.token

        started_at = time.monotonic()
        response = self.request(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "scope": "icdapi_access",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        data = read_response(response, "WHO OAuth")

        try:
            token = data["access_token"]
            expires_in = int(data["expires_in"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ICDError("WHO returned an invalid token response.") from None

        if not isinstance(token, str) or not token.strip() or expires_in <= 0:
            raise ICDError("WHO returned an invalid token response.")

        self.token = token
        self.token_expires_at = started_at + expires_in - min(30, expires_in / 2)
        return self.token

    def search_icd11(self, term, traditional=False):
        term = term.strip()
        if not term:
            raise ICDError("Enter a search term.")

        url = f"{API_URL}/{self.release}/mms/search"
        params = {
            "q": term,
            "highlightingEnabled": "false",
            "flatResults": "true",
        }

        if traditional:
            params["chapterFilter"] = "26"
            if self.tm2_subtree:
                params["subtreesFilter"] = self.tm2_subtree

        for attempt in range(2):
            response = self.request(
                "GET",
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {self.get_token()}",
                    "API-Version": "v2",
                    "Accept": "application/json",
                    "Accept-Language": self.language,
                },
            )
            if response.status_code != 401 or attempt == 1:
                break
            self.token = ""

        data = read_response(response, "ICD-11 search")
        results = data.get("destinationEntities")

        if data.get("error") or not isinstance(results, list):
            raise ICDError("WHO returned an unexpected search response.")

        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search WHO ICD-11 terminology.")
    parser.add_argument("term", help="Term to search for")
    parser.add_argument("--traditional", action="store_true", help="Search Chapter 26")
    args = parser.parse_args()

    try:
        results = ICDClient().search_icd11(args.term, args.traditional)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    except ICDError as error:
        parser.exit(1, f"Error: {error}\n")