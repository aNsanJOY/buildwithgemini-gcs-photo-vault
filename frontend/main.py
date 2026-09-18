"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import json
import os
import re
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request, UploadFile, File, Form, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


_A2UI_KEYS = ("beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface")


def _extract_a2ui_from_text(text: str) -> tuple[list[dict], str]:
    """Extract A2UI JSON messages from text and return (a2ui_messages, clean_text)."""
    if not any(k in text for k in _A2UI_KEYS):
        return [], text

    a2ui_messages = []

    def _parse_and_collect(raw_json_str: str):
        try:
            val = json.loads(raw_json_str)
            if isinstance(val, list):
                a2ui_messages.extend(val)
            elif isinstance(val, dict):
                a2ui_messages.append(val)
        except Exception:
            decoder = json.JSONDecoder()
            idx = 0
            n = len(raw_json_str)
            while idx < n:
                while idx < n and raw_json_str[idx] not in "{[":
                    idx += 1
                if idx >= n:
                    break
                try:
                    v, end = decoder.raw_decode(raw_json_str, idx)
                    if isinstance(v, list):
                        a2ui_messages.extend(v)
                    elif isinstance(v, dict):
                        a2ui_messages.append(v)
                    idx = end
                except Exception:
                    idx += 1

    working = text

    def repl_a2ui(m):
        _parse_and_collect(m.group(1).strip())
        return ""

    def repl_datapart(m):
        raw = m.group(1).strip()
        try:
            val = json.loads(raw)
            if isinstance(val, dict) and "data" in val:
                d = val["data"]
                if isinstance(d, list):
                    a2ui_messages.extend(d)
                elif isinstance(d, dict):
                    a2ui_messages.append(d)
            else:
                _parse_and_collect(raw)
        except Exception:
            _parse_and_collect(raw)
        return ""

    working = re.sub(r"<a2ui-json>\s*([\s\S]*?)\s*</a2ui-json>", repl_a2ui, working, flags=re.IGNORECASE)
    working = re.sub(r"<a2a_datapart_json>\s*([\s\S]*?)\s*</a2a_datapart_json>", repl_datapart, working, flags=re.IGNORECASE)

    if not a2ui_messages:
        def repl_codeblock(m):
            code = m.group(1).strip()
            if any(k in code for k in _A2UI_KEYS):
                before_count = len(a2ui_messages)
                _parse_and_collect(code)
                if len(a2ui_messages) > before_count:
                    return ""
            return m.group(0)

        working = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", repl_codeblock, working, flags=re.IGNORECASE)

    clean_text = re.sub(r"\n\s*\n\s*\n", "\n\n", working).strip()
    return a2ui_messages, clean_text


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Text parts pass through as {"kind": "text"}. A2UI data parts (tagged
    application/json+a2ui) become {"kind": "a2ui", "data": <message>} so the UI
    renders the card; each data part is one A2UI message (beginRendering or
    surfaceUpdate).
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        if isinstance(root, TextPart) and getattr(root, "text", None):
            a2ui_msgs, clean_text = _extract_a2ui_from_text(root.text)
            if clean_text:
                out.append({"kind": "text", "text": clean_text})
            for m in a2ui_msgs:
                out.append({"kind": "a2ui", "data": m})
        elif getattr(root, "data", None) is not None:
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": root.data})
        elif isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if not isinstance(event, tuple):
                continue
            task, update = event
            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                got_artifact_update = True
                parts.extend(_extract_parts(update.artifact.parts))

        # Fallback: pull parts from final task artifacts or status message if empty
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))
            if not parts and getattr(last_task, "status", None) and getattr(last_task.status, "message", None):
                msg_parts = getattr(last_task.status.message, "parts", []) or []
                parts.extend(_extract_parts(msg_parts))

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


import os
import datetime
from google.cloud import storage, firestore

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-01-881fc83d76ea")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", f"gcs-photo-vault-{PROJECT_ID}")


@app.get("/image_proxy")
async def image_proxy(url: str):
    """Proxy GCS images to the browser using GCP credentials if direct access fails."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    bucket_name = None
    blob_name = None
    if url.startswith("gs://"):
        parts = url[5:].split("/", 1)
        if len(parts) == 2:
            bucket_name, blob_name = parts[0], parts[1]
    elif "storage.googleapis.com/" in url:
        parts = url.split("storage.googleapis.com/", 1)[1].split("/", 1)
        if len(parts) == 2:
            bucket_name, blob_name = parts[0], parts[1]

    if bucket_name and blob_name:
        blob_name = re.sub(r"[\*\.\,><`\]]+$", "", blob_name)
        try:
            storage_client = storage.Client(project=PROJECT_ID)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            content = blob.download_as_bytes()
            content_type = blob.content_type or "image/jpeg"
            return Response(content=content, media_type=content_type)
        except Exception as e:
            print(f"Image proxy error for {bucket_name}/{blob_name}: {e}")
            raise HTTPException(status_code=404, detail="Image not found")

    raise HTTPException(status_code=400, detail="Invalid storage URL")


@app.post("/upload")
async def upload_photos(
    files: list[UploadFile] = File(...),
    tagged_people: str = Form(""),
    special_moment: str = Form(""),
    user_email: str = Form("guest@example.com"),
):
    """Uploads single or bulk photo files to GCS and saves metadata in Firestore."""
    storage_client = storage.Client(project=PROJECT_ID)
    db = firestore.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)

    people_list = (
        [p.strip() for p in tagged_people.split(",") if p.strip()]
        if tagged_people
        else []
    )
    uploaded_records = []

    for file in files:
        file_bytes = await file.read()
        unique_id = str(uuid.uuid4())[:8]
        original_name = file.filename or "photo.jpg"
        clean_filename = original_name.replace(" ", "_")
        blob_name = f"uploads/{unique_id}_{clean_filename}"

        blob = bucket.blob(blob_name)
        content_type = file.content_type or "image/jpeg"
        blob.upload_from_string(file_bytes, content_type=content_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
        gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
        photo_id = f"photo_upload_{unique_id}"

        title = clean_filename.rsplit(".", 1)[0].replace("_", " ").title()
        doc_data = {
            "photo_id": photo_id,
            "filename": original_name,
            "title": title,
            "gcs_uri": gcs_uri,
            "public_url": public_url,
            "storage_class": "STANDARD",
            "tagged_people": people_list,
            "special_moment": special_moment or "User Upload",
            "uploaded_by": user_email,
            "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        db.collection("photo_memories").document(photo_id).set(doc_data)
        uploaded_records.append(doc_data)

    return JSONResponse(
        {
            "status": "success",
            "count": len(uploaded_records),
            "uploaded": uploaded_records,
        }
    )


@app.post("/archive-coldline")
async def archive_to_coldline():
    """Transitions all photo memories in Firestore and GCS to COLDLINE storage class on UI close."""
    try:
        db = firestore.Client(project=PROJECT_ID)
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)

        updated_count = 0
        docs = db.collection("photo_memories").stream()
        for doc in docs:
            doc.reference.update({"storage_class": "COLDLINE"})
            updated_count += 1

        try:
            blobs = bucket.list_blobs()
            for blob in blobs:
                if blob.storage_class != "COLDLINE":
                    blob.update_storage_class("COLDLINE")
        except Exception as e:
            print(f"GCS blob storage class transition warning: {e}")

        return JSONResponse(
            {
                "status": "success",
                "message": f"Migrated {updated_count} photo memories to COLDLINE storage class.",
                "count": updated_count,
            }
        )
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/delete-photos")
async def delete_photos_endpoint(req: Request):
    """Deletes multiple photo/video memory records permanently from both Firestore and GCS bucket."""
    try:
        body = await req.json()
        photo_ids = body.get("photo_ids") or []
        photo_urls = body.get("photo_urls") or []

        db = firestore.Client(project=PROJECT_ID)
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)

        deleted_firestore_count = 0
        deleted_gcs_count = 0

        # 1. Delete matching Firestore documents & associated GCS blobs
        all_docs = list(db.collection("photo_memories").stream())
        for doc in all_docs:
            data = doc.to_dict() or {}
            doc_id = doc.id
            pid = data.get("photo_id", doc_id)
            purl = data.get("public_url", "")
            guri = data.get("gcs_uri", "")

            should_delete = (
                doc_id in photo_ids
                or pid in photo_ids
                or purl in photo_urls
                or guri in photo_urls
                or any(
                    target
                    and (target in purl or target in guri or target in pid or target in doc_id)
                    for target in photo_ids + photo_urls
                )
            )

            if should_delete:
                doc.reference.delete()
                deleted_firestore_count += 1

                # Extract and delete GCS Blob
                target_url = purl or guri or f"{pid}.jpg"
                blob_name = None
                if f"/{BUCKET_NAME}/" in target_url:
                    blob_name = target_url.split(f"/{BUCKET_NAME}/")[-1]
                elif target_url.startswith("gs://"):
                    blob_name = target_url.replace(f"gs://{BUCKET_NAME}/", "")
                else:
                    blob_name = target_url.split("/")[-1]

                if blob_name:
                    try:
                        blob = bucket.blob(blob_name)
                        if blob.exists():
                            blob.delete()
                            deleted_gcs_count += 1
                    except Exception as err:
                        print(f"GCS deletion notice for {blob_name}: {err}")

        # 2. Direct GCS Object Deletion for any uploaded blobs
        for raw_url in photo_urls:
            blob_name = None
            if f"/{BUCKET_NAME}/" in raw_url:
                blob_name = raw_url.split(f"/{BUCKET_NAME}/")[-1]
            elif raw_url.startswith("gs://"):
                blob_name = raw_url.replace(f"gs://{BUCKET_NAME}/", "")
            elif "/" in raw_url:
                blob_name = raw_url.split("/")[-1]

            if blob_name:
                try:
                    blob = bucket.blob(blob_name)
                    if blob.exists():
                        blob.delete()
                        deleted_gcs_count += 1
                except Exception as err:
                    print(f"Direct GCS deletion notice for {blob_name}: {err}")

        return JSONResponse(
            {
                "status": "success",
                "message": f"Successfully deleted {deleted_firestore_count} Firestore memory record(s) and {deleted_gcs_count} GCS storage object(s).",
                "deleted_firestore": deleted_firestore_count,
                "deleted_gcs": deleted_gcs_count,
            }
        )
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
