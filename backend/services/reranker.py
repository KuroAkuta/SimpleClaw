"""
DashScope Reranker service.
"""
import os
from typing import Dict, List, Optional
import requests

from config.settings import settings


class DashScopeRerank:
    """
    DashScope Reranker service.

    Usage:
        reranker = DashScopeRerank()
        results = reranker.rerank(query, documents, top_n=5)
    """

    def __init__(
        self,
        model: str = None,
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
    ):
        self.model = model or settings.RERANKER_MODEL
        self.api_key = api_key or settings.RERANKER_API_KEY
        self.base_url = base_url

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = 5,
    ) -> List[Dict]:
        """
        Rerank documents based on query relevance.

        Args:
            query: Search query
            documents: List of document texts
            top_n: Number of top results to return

        Returns:
            List of dicts with index, text, and relevance score
        """
        url = f"{self.base_url}/services/rerank/text-rerank/text-rerank"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "return_documents": True,
                "top_n": top_n,
            },
        }

        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        print(f"Rerank response: {data}")  # Debug output

        # Check for error - DashScope returns code as string or integer
        code = data.get("code")
        if code and str(code) != "200":
            raise Exception(f"Rerank error: {data.get('message', 'Unknown error')}")

        results = data.get("output", {}).get("results", [])

        if not results:
            # Try alternate response format
            output = data.get("output", {})
            if output:
                results = output.get("results", [])

        return [
            {
                "index": item.get("index", i),
                "text": item.get("document", {}).get("text", documents[item.get("index", i)]),
                "score": item.get("relevance_score", 0),
            }
            for i, item in enumerate(results)
        ]
