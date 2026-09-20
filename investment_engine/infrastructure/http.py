from __future__ import annotations
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(self, timeout: float = 15.0, retries: int = 3):
        self.timeout = timeout
        self.session = requests.Session()
        retries = max(0, min(int(retries), 5))
        retry = Retry(total=retries, connect=retries, read=retries, backoff_factor=0.5,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"User-Agent": "Mozilla/5.0 InvestmentEngine/0.1"})

    def get(self, url: str, **kwargs) -> requests.Response:
        r = self.session.get(url, timeout=kwargs.pop("timeout", self.timeout), **kwargs)
        r.raise_for_status()
        return r

    def post(self, url: str, **kwargs) -> requests.Response:
        r = self.session.post(url, timeout=kwargs.pop("timeout", self.timeout), **kwargs)
        r.raise_for_status()
        return r
