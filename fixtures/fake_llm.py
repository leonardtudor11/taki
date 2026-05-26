"""Canned LLM responses for offline department tests.

Each fake returns JSON that matches a department schema and cites snippets that
exist in fixtures.sample.sample_bundle(), so grounding passes.
"""

from __future__ import annotations

import json


def fake_gtm_llm(_prompt: str) -> str:
    return json.dumps(
        {
            "target": "Northwind Analytics",
            "buying_signals": [
                {
                    "text": "Recently raised a large round to expand into the EU.",
                    "citations": [
                        {
                            "url": "https://news.example/northwind-series-b",
                            "snippet": "closed a $40M Series B led by Acme Ventures",
                            "source_type": "news",
                        }
                    ],
                    "confidence": 0.8,
                }
            ],
            "competitor_moves": [],
            "hiring_signals": [
                {
                    "text": "Scaling enterprise sales headcount.",
                    "citations": [
                        {
                            "url": "https://northwind.example/careers",
                            "snippet": "hiring 12 enterprise account executives",
                            "source_type": "jobs",
                        }
                    ],
                    "confidence": 0.9,
                }
            ],
            "outreach_angle": "Congratulate on the Series B; tie to EU go-to-market.",
        }
    )


def fake_finance_llm(_prompt: str) -> str:
    return json.dumps(
        {
            "target": "Northwind Analytics",
            "pricing_trend": [
                {
                    "text": "Raised Pro pricing ~60% and dropped the free tier.",
                    "citations": [
                        {
                            "url": "https://northwind.example/pricing",
                            "snippet": "raised its Pro plan from $49 to $79",
                            "source_type": "pricing",
                        }
                    ],
                    "confidence": 0.9,
                }
            ],
            "expansion_contraction": [
                {
                    "text": "Headcount expansion signals growth.",
                    "citations": [
                        {
                            "url": "https://northwind.example/careers",
                            "snippet": "hiring 12 enterprise account executives",
                            "source_type": "jobs",
                        }
                    ],
                    "confidence": 0.7,
                }
            ],
            "web_traffic_proxy": [],
            "vendor_health_flags": [],
        }
    )


def fake_security_llm(_prompt: str) -> str:
    return json.dumps(
        {
            "target": "Northwind Analytics",
            "exposure_indicators": [],
            "reputational_signals": [
                {
                    "text": "Support quality complaints after pricing change.",
                    "citations": [
                        {
                            "url": "https://reviews.example/northwind",
                            "snippet": "report slow support response times",
                            "source_type": "review",
                        }
                    ],
                    "confidence": 0.6,
                }
            ],
            "regulatory_signals": [],
            "third_party_risk": [],
        }
    )
