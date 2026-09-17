# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types


# WRITE: after each turn, send the session to Memory Bank for extraction.
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


import os
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.code_executors import AgentEngineSandboxCodeExecutor

from app.a2ui_utils import a2ui_callback
from app.tools.firestore_tools import (
    get_photo_memory,
    list_photo_memories,
    save_photo_memory,
)
from app.tools.image_generation_tool import generate_domain_image
from app.tools.public_photo_tool import search_public_photos
from app.tools.storage_calculator_tool import calculate_storage_cost_savings
from app.tools.video_generation_tool import generate_domain_video

AGENT_ENGINE_RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/104993709195/locations/us-east1/reasoningEngines/3157436755158761472",
)

sandbox_code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=AGENT_ENGINE_RESOURCE
)

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an AI assistant for Cloud Media & Memory Manager (GCS Photo Vault). "
        "Your primary role is to help users manage their photo memories in Google Cloud Storage while "
        "actively remembering key details about their life."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

full_instruction = (
    f"{a2ui_instruction}\n\n"
    "MEMORY & MEDIA GUIDELINES:\n"
    "1. VERSATILE MEDIA VAULT: The user stores all types of images and videos in GCS (friends/family, nature, travel, food, pets, hobbies, art, documents, receipts, etc.). Treat media as general memories.\n"
    "2. PEOPLE & RELATIONSHIPS: Remember names of people, family members, pets, and companions featured in photos or videos when specified.\n"
    "3. MOMENTS & EVENTS: Record and recall dates, places, events, topics, celebrations, and categories associated with media.\n"
    "4. STORAGE & PHOTO PREFERENCES: Remember media tagging preferences, favorite categories, and GCS storage class settings "
    "(Standard, Nearline, Coldline, Archive).\n"
    "5. DATABASE & SEARCH: Use list_photo_memories, get_photo_memory, and save_photo_memory for photo records. "
    "Use calculate_storage_cost_savings to calculate monthly cost savings when moving photo libraries between storage classes. "
    "Use search_public_photos to find free public domain photos. "
    "Use generate_domain_image to generate AI photos/memories using gemini-3.1-flash-lite-image and store them in GCS & artifacts. "
    "Use generate_domain_video to generate AI short videos using gemini-omni-flash-preview and store them in GCS & artifacts. "
    "Use python code execution in your sandbox environment to analyze data, calculate metrics, or run complex media calculations."
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=full_instruction,
    tools=[
        get_weather,
        get_current_time,
        PreloadMemoryTool(),
        list_photo_memories,
        get_photo_memory,
        save_photo_memory,
        calculate_storage_cost_savings,
        search_public_photos,
        generate_domain_image,
        generate_domain_video,
    ],
    code_executor=sandbox_code_executor,
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

