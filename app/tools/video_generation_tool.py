"""Video generation tool for GCS Photo Vault using gemini-omni-flash-preview."""

import base64
import os
import time
from google import genai
from google.cloud import storage
from google.genai import types
from google.adk.tools import ToolContext

RAW_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-01-881fc83d76ea")
PROJECT_ID = "qwiklabs-gcp-01-881fc83d76ea" if (not RAW_PROJECT_ID or RAW_PROJECT_ID.isdigit()) else RAW_PROJECT_ID
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME") or f"gcs-photo-vault-{PROJECT_ID}"


def generate_domain_video(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates a short video for photo memories or domain topics using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the generated video as an artifact for Playground display, uploads the video bytes directly
    to the GCS Photo Vault bucket, and saves the video record in Firestore.

    Args:
        prompt: Highly detailed, vivid description of the video/scene to generate (e.g., 'A golden retriever running through vibrant autumn leaves on a sunny park trail', 'Cinematic video of sunset over ocean waves crashing on a sandy beach'). Always expand the prompt with full user context and visual details.
        tool_context: ToolContext automatically injected by ADK for artifact saving.

    Returns:
        Confirmation string containing artifact details, GCS URI, and public video URL.
    """
    enhanced_prompt = (
        f"Generate a vivid, high-quality, realistic short video depicting the following specific scene: {prompt}. "
        f"Ensure all visual elements, subjects, motion, and atmosphere precisely match: {prompt}."
    )

    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    interaction = client.interactions.create(
        model="gemini-omni-flash-preview",
        input=enhanced_prompt,
    )

    if not hasattr(interaction, "output_video") or not interaction.output_video or not interaction.output_video.data:
        return "Failed to generate video output from gemini-omni-flash-preview model."

    raw_data = interaction.output_video.data
    if isinstance(raw_data, str):
        video_bytes = base64.b64decode(raw_data)
    else:
        video_bytes = raw_data

    mime_type = getattr(interaction.output_video, "mime_type", None) or "video/mp4"

    timestamp = int(time.time())
    filename = f"generated_video_{timestamp}.mp4"

    # 1. Save artifact with tool_context (for Playground Artifacts panel)
    if tool_context is not None:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload video bytes directly to GCS bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"generated_videos/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

    # 3. Save memory record in Firestore (Firebase)
    try:
        from google.cloud import firestore
        db = firestore.Client(project=PROJECT_ID)
        photo_id = f"generated_video_{timestamp}"
        title = f"Generated Video: {prompt[:30].strip()}"
        doc_data = {
            "photo_id": photo_id,
            "filename": filename,
            "title": title,
            "gcs_uri": gcs_uri,
            "public_url": public_url,
            "storage_class": "STANDARD",
            "special_moment": "Generated Video Memory",
            "tagged_friends": [],
            "tags": ["generated", "video", "ai"],
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        db.collection("photo_memories").document(photo_id).set(doc_data)
    except Exception as e:
        print(f"Warning: Could not save generated video to Firestore: {e}")

    return (
        f"Successfully generated video for prompt: '{prompt}'\n"
        f"• Artifact Saved: {filename}\n"
        f"• GCS URI: {gcs_uri}\n"
        f"• Public URL: {public_url}"
    )
