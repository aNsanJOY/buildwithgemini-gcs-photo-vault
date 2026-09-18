"""Image generation tool for GCS Photo Vault using gemini-3.1-flash-lite-image."""

import os
import time
from google import genai
from google.cloud import storage
from google.genai import types
from google.adk.tools import ToolContext

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-01-881fc83d76ea")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", f"gcs-photo-vault-{PROJECT_ID}")


def generate_domain_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates an image for photo memories or scenery using gemini-3.1-flash-lite-image in the global region.

    Saves the generated image as an artifact for Playground display and uploads the image bytes directly
    to the GCS Photo Vault bucket.

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

    return (
        f"Successfully generated photo for prompt: '{prompt}'\n"
        f"• Artifact Saved: {filename}\n"
        f"• GCS URI: {gcs_uri}\n"
        f"• Public URL: {public_url}"
    )
