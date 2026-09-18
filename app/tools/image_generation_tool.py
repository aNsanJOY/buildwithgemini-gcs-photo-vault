"""Image generation tool for GCS Photo Vault using gemini-3.1-flash-lite-image."""

import os
import time
from google import genai
from google.cloud import storage
from google.genai import types
from google.adk.tools import ToolContext

RAW_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-01-881fc83d76ea")
PROJECT_ID = "qwiklabs-gcp-01-881fc83d76ea" if (not RAW_PROJECT_ID or RAW_PROJECT_ID.isdigit()) else RAW_PROJECT_ID
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME") or f"gcs-photo-vault-{PROJECT_ID}"


def generate_domain_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates an image for photo memories or scenery using gemini-3.1-flash-lite-image in the global region.

    Saves the generated image as an artifact for Playground display, uploads the image bytes directly
    to the GCS Photo Vault bucket, and saves the photo record in Firestore.

    Args:
        prompt: Description of the image/scene to generate (e.g., 'Kyoto cherry blossoms at sunset', 'Yosemite mountain hike').
        tool_context: ToolContext automatically injected by ADK for artifact saving.

    Returns:
        Confirmation string containing artifact details, GCS URI, and public image URL.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    if not response.candidates or not response.candidates[0].content.parts:
        return "Failed to generate image response from model."

    part = response.candidates[0].content.parts[0]
    if not part.inline_data:
        return "No image byte data returned by the model."

    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"

    timestamp = int(time.time())
    filename = f"generated_memory_{timestamp}.jpg"

    # 1. Save artifact with tool_context (for Playground Artifacts panel)
    if tool_context is not None:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload image bytes directly to GCS bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"generated_photos/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

    # 3. Save memory record in Firestore (Firebase)
    try:
        from google.cloud import firestore
        db = firestore.Client(project=PROJECT_ID)
        photo_id = f"generated_{timestamp}"
        title = f"Generated: {prompt[:30].strip()}"
        doc_data = {
            "photo_id": photo_id,
            "filename": filename,
            "title": title,
            "gcs_uri": gcs_uri,
            "public_url": public_url,
            "storage_class": "STANDARD",
            "special_moment": "Generated Photo Memory",
            "tagged_friends": [],
            "tags": ["generated", "ai"],
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        db.collection("photo_memories").document(photo_id).set(doc_data)
    except Exception as e:
        print(f"Warning: Could not save generated image to Firestore: {e}")

    return (
        f"Successfully generated photo for prompt: '{prompt}'\n"
        f"• Artifact Saved: {filename}\n"
        f"• GCS URI: {gcs_uri}\n"
        f"• Public URL: {public_url}"
    )
