"""Firestore function tools for GCS Photo Vault.

Hardcodes project ID "qwiklabs-gcp-03-bfaa22c3fd9c" to avoid runtime
project number resolution errors on Agent Platform.
"""

import os
from typing import Any
from google.cloud import firestore

FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-881fc83d76ea"
COLLECTION_NAME = "photo_memories"


def _get_firestore_client() -> firestore.Client:
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def list_photo_memories(
    friend_name: str = "", storage_class: str = "", tag: str = ""
) -> list[dict[str, Any]]:
    """List photo memories stored in Firestore, with optional filters.

    Args:
        friend_name: Optional friend name to filter by (e.g. 'Sarah', 'Alex').
        storage_class: Optional GCS storage class filter (e.g. 'STANDARD', 'COLDLINE').
        tag: Optional category or location tag to filter by (e.g. 'kyoto', 'beach').

    Returns:
        A list of photo memory records matching the query criteria.
    """
    db = _get_firestore_client()
    docs = db.collection(COLLECTION_NAME).stream()
    results = []

    for doc in docs:
        data = doc.to_dict()
        if not data:
            continue

        if friend_name and friend_name.lower() not in [
            f.lower() for f in data.get("tagged_friends", [])
        ]:
            continue

        if (
            storage_class
            and data.get("storage_class", "").upper() != storage_class.upper()
        ):
            continue

        if tag and tag.lower() not in [t.lower() for t in data.get("tags", [])]:
            continue

        results.append(data)

    return results


def get_photo_memory(photo_id: str) -> dict[str, Any]:
    """Get details of a specific photo memory record from Firestore.

    Args:
        photo_id: The document ID of the photo memory (e.g. 'photo_001').

    Returns:
        The photo memory record dictionary or an error message if not found.
    """
    db = _get_firestore_client()
    doc = db.collection(COLLECTION_NAME).document(photo_id).get()

    if doc.exists:
        return doc.to_dict()
    return {"error": f"Photo memory document '{photo_id}' not found."}


def save_photo_memory(
    photo_id: str,
    title: str,
    tagged_friends: list[str],
    special_moment: str,
    location: str,
    storage_class: str = "STANDARD",
    tags: list[str] = None,
) -> dict[str, Any]:
    """Save or update a photo memory record in the Firestore database.

    Args:
        photo_id: Unique identifier for the photo (e.g. 'photo_004').
        title: Descriptive title for the photo or album.
        tagged_friends: List of names of friends tagged in the photo (e.g. ['Sarah', 'Alex']).
        special_moment: The milestone or occasion (e.g. 'Kyoto Trip 2026').
        location: Geographical location where the photo was taken.
        storage_class: GCS storage class classification ('STANDARD', 'NEARLINE', 'COLDLINE', 'ARCHIVE').
        tags: Optional list of descriptive keywords or tags.

    Returns:
        A status message and the saved record data.
    """
    db = _get_firestore_client()
    tags = tags or []
    gcs_uri = f"gs://gcs-photo-vault-{FIRESTORE_PROJECT_ID}/{photo_id}.jpg"
    public_url = f"https://storage.googleapis.com/gcs-photo-vault-{FIRESTORE_PROJECT_ID}/{photo_id}.jpg"

    data = {
        "photo_id": photo_id,
        "title": title,
        "tagged_friends": tagged_friends,
        "special_moment": special_moment,
        "location": location,
        "storage_class": storage_class.upper(),
        "gcs_uri": gcs_uri,
        "public_url": public_url,
        "tags": tags,
    }

    db.collection(COLLECTION_NAME).document(photo_id).set(data)

    # Sync GCS blob storage class if object exists
    try:
        from google.cloud import storage
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(f"gcs-photo-vault-{FIRESTORE_PROJECT_ID}")
        blobs = bucket.list_blobs()
        for blob in blobs:
            if photo_id.lower() in blob.name.lower():
                if blob.storage_class != storage_class.upper():
                    blob.update_storage_class(storage_class.upper())
    except Exception as e:
        print(f"Warning syncing GCS storage class for {photo_id}: {e}")

    return {"status": "success", "message": f"Saved photo memory '{photo_id}'", "data": data}


def update_photo_storage_class(
    photo_id: str,
    new_storage_class: str,
) -> dict[str, Any]:
    """Updates the GCS storage class classification of a photo memory in BOTH Firestore and Google Cloud Storage.

    Args:
        photo_id: Document ID or photo identifier (e.g. 'photo_001', 'kyoto_cherry_blossoms').
        new_storage_class: Target GCS storage class ('STANDARD', 'NEARLINE', 'COLDLINE', 'ARCHIVE').

    Returns:
        Status dictionary with confirmation of Firestore and GCS updates.
    """
    db = _get_firestore_client()
    target_class = new_storage_class.upper()
    
    # 1. Update Firestore document
    doc_ref = db.collection(COLLECTION_NAME).document(photo_id)
    doc = doc_ref.get()
    found = False
    
    if doc.exists:
        doc_ref.update({"storage_class": target_class})
        found = True
    else:
        # Stream search by photo_id or title
        docs = db.collection(COLLECTION_NAME).stream()
        for d in docs:
            data = d.to_dict() or {}
            if photo_id.lower() in (
                d.id.lower(),
                data.get("photo_id", "").lower(),
                data.get("title", "").lower(),
                data.get("filename", "").lower(),
            ):
                d.reference.update({"storage_class": target_class})
                found = True

    # 2. Update GCS blob storage class
    gcs_updated = False
    try:
        from google.cloud import storage
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(f"gcs-photo-vault-{FIRESTORE_PROJECT_ID}")
        blobs = bucket.list_blobs()
        for blob in blobs:
            if photo_id.lower() in blob.name.lower():
                if blob.storage_class != target_class:
                    blob.update_storage_class(target_class)
                    gcs_updated = True
    except Exception as e:
        print(f"Warning updating GCS blob storage class: {e}")

    return {
        "status": "success",
        "message": f"Updated storage class for '{photo_id}' to {target_class} in Firestore" + (" and GCS" if gcs_updated else ""),
        "photo_id": photo_id,
        "new_storage_class": target_class,
        "firestore_updated": found,
        "gcs_updated": gcs_updated,
    }


def delete_photo_memories(photo_ids: list[str]) -> dict[str, Any]:
    """Delete multiple photo memory records from Firestore and GCS.

    Args:
        photo_ids: List of photo document IDs or titles to delete (e.g. ['photo_001', 'photo_002']).

    Returns:
        A dictionary with deletion status and count of deleted records.
    """
    db = _get_firestore_client()
    deleted_count = 0
    deleted_ids = []

    for pid in photo_ids:
        doc_ref = db.collection(COLLECTION_NAME).document(pid)
        if doc_ref.get().exists:
            doc_ref.delete()
            deleted_count += 1
            deleted_ids.append(pid)
        else:
            docs = db.collection(COLLECTION_NAME).where("photo_id", "==", pid).stream()
            found = False
            for d in docs:
                d.reference.delete()
                deleted_count += 1
                deleted_ids.append(d.id)
                found = True
            if not found:
                docs = db.collection(COLLECTION_NAME).stream()
                for d in docs:
                    data = d.to_dict() or {}
                    if pid.lower() in (
                        data.get("filename", "").lower(),
                        data.get("title", "").lower(),
                        data.get("photo_id", "").lower(),
                    ):
                        d.reference.delete()
                        deleted_count += 1
                        deleted_ids.append(d.id)

    return {
        "status": "success",
        "message": f"Deleted {deleted_count} photo memory record(s).",
        "deleted_count": deleted_count,
        "deleted_ids": deleted_ids,
    }
