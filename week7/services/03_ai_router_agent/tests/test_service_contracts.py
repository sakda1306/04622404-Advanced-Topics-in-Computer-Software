import json
import unittest
from pathlib import Path

import httpx

from app.clients import ServiceClients
from app.router import Router
from app.teams import TeamDirectory


class ServiceContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.search_status = 200
        self.predict_status = 200
        self.queries = []

        def respond(request):
            self.queries.append(dict(request.url.params))
            self.calls.append((request.url.path, json.loads(request.content) if request.content else None,
                               request.headers.get("X-Request-ID")))
            path = request.url.path
            if path == "/football/teams":
                return httpx.Response(200, json={"teams": [{"team_id": 57, "name": "Arsenal FC",
                                                               "short_name": "Arsenal", "aliases": ["ปืนใหญ่"]}]})
            if path == "/search":
                if self.search_status != 200:
                    return httpx.Response(self.search_status)
                return httpx.Response(200, json={"chunks": [{"text": "Arsenal won 1-0",
                    "source": {"doc_id": "match-1", "title": "Arsenal result", "category": "match_report",
                               "origin": "football-data.org", "ref": 1}}]})
            if path == "/generate":
                payload = json.loads(request.content)
                return httpx.Response(200, json={"answer": "Arsenal won 1-0",
                                                 "sources": [item["source"] for item in payload["contexts"]]})
            if path == "/football/predict":
                if self.predict_status != 200:
                    return httpx.Response(self.predict_status, json={"code": "SIMULATION_UNAVAILABLE"})
                return httpx.Response(200, json={"content": "Home 40%", "data": {"as_of": None}})
            if path == "/general":
                return httpx.Response(200, json={"content": "Football rule"})
            if path == "/local/classify":
                return httpx.Response(200, json={"data": {"label": "general_football", "score": 0.9}})
            raise AssertionError(path)

        self.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        self.clients = ServiceClients(self.http)
        teams = TeamDirectory.from_file(Path(__file__).parents[1] / "data" / "team_aliases.json")
        self.router = Router(self.clients, teams)

    async def asyncTearDown(self):
        await self.http.aclose()

    async def route(self, query):
        return await self.router.route({"request_id": "contract-1", "query": query, "history": [],
            "user": {"language": "th"}, "context": {"season": "2026", "now": "2026-09-26T10:00:00+07:00"}})

    async def test_football_teams_response(self):
        payload = await self.clients.get_teams()
        self.assertEqual(payload["teams"][0]["team_id"], 57)

    async def test_retrieval_to_generation_keeps_citation_and_request_id(self):
        result = await self.route("เมื่อวานปืนใหญ่ชนะไหม")
        self.assertEqual(result["route"], "football_rag")
        self.assertEqual(result["sources"][0]["doc_id"], "match-1")
        self.assertEqual([call[0] for call in self.calls], ["/search", "/generate"])
        self.assertTrue(all(call[2] == "contract-1" for call in self.calls))

    async def test_prediction_calls_football_data_with_team_ids(self):
        await self.route("ทำนายผล แมนซิตี้ กับ ลิเวอร์พูล")
        path, _body, request_id = self.calls[0]
        self.assertEqual(path, "/football/predict")
        self.assertEqual(request_id, "contract-1")
        self.assertEqual(self.queries[0], {"home_team_id": "65", "away_team_id": "64"})

    async def test_prediction_503_and_index_503(self):
        self.predict_status = 503
        result = await self.route("ทำนายผล แมนซิตี้ กับ ลิเวอร์พูล")
        self.assertEqual(result["trace"]["fallback"], "simulation_down")
        self.search_status = 503
        result = await self.route("เมื่อวานปืนใหญ่ชนะไหม")
        self.assertEqual(result["trace"]["fallback"], "retrieval_down")
        self.assertEqual(result["route"], "football_rag")
