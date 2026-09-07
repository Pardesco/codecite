import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.conftest import TEST_URL


def _params():
    env = {**os.environ, "CODEPLUMB_DATABASE_URL": TEST_URL, "CODEPLUMB_EMBED_PROVIDER": "fake"}
    return StdioServerParameters(command=sys.executable, args=["-m", "codeplumb.cli", "serve"], env=env)


def _text(result):
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_mcp_tools_resources_prompts(db):
    async with stdio_client(_params()) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            assert {"search_code", "get_section", "get_context", "resolve_reference", "list_corpora", "list_chapters"} <= tools
            assert "ingest_document" not in tools  # off by default

            corpora = await s.call_tool("list_corpora", {})
            assert not corpora.is_error
            assert any(c["id"] == "sample-bc-2026" for c in (json.loads(x.text) for x in corpora.content))

            res = await s.call_tool("search_code", {"query": "occupant load factor business areas", "corpora": ["sample-bc-2026"], "k": 3})
            assert not res.is_error
            data = _text(res)
            assert data["hits"][0]["section"]["number"] == "1004.5"
            assert "citation" in data["hits"][0]

            sec = await s.call_tool("get_section", {"number": "1017.2", "corpus": "sample-bc-2026"})
            assert _text(sec)["tables"]

            bad = await s.call_tool("get_section", {"number": "1017.99", "corpus": "sample-bc-2026"})
            assert bad.is_error
            assert "nearest" in bad.content[0].text

            ch = await s.call_tool("list_chapters", {"corpus": "sample-bc-2026"})
            assert any(c["number"] == "10" for c in (json.loads(x.text) for x in ch.content))

            templates = {t.uri_template for t in (await s.list_resource_templates()).resource_templates}
            assert "codeplumb://{corpus}/section/{number}" in templates
            page = await s.read_resource("codeplumb://sample-bc-2026/section/1004.5")
            assert "§1004.5" in page.contents[0].text

            prompts = {p.name for p in (await s.list_prompts()).prompts}
            assert {"code_question", "compare_to_standard"} <= prompts
            p = await s.get_prompt("code_question", {"question": "corridor width?"})
            assert "search_code" in p.messages[0].content.text
