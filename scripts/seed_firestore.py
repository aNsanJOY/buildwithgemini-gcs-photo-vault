"""Seed script to populate Firestore with sample photo memories."""

from google.cloud import firestore
import google.auth

PROJECT_ID = "qwiklabs-gcp-03-bfaa22c3fd9c"
BUCKET_NAME = f"gcs-photo-vault-{PROJECT_ID}"
COLLECTION_NAME = "photo_memories"


def seed_database():
    credentials, _ = google.auth.default()
    db = firestore.Client(project=PROJECT_ID, credentials=credentials)

    seed_items = [
        {
            "photo_id": "photo_001",
            "title": "Kyoto Cherry Blossoms with Sarah",
            "tagged_friends": ["Sarah"],
            "special_moment": "Sarah's 30th Birthday Trip",
            "location": "Kyoto, Japan",
            "storage_class": "STANDARD",
            "gcs_uri": f"gs://{BUCKET_NAME}/kyoto/cherry_blossoms_01.jpg",
            "public_url": f"https://storage.googleapis.com/{BUCKET_NAME}/kyoto/cherry_blossoms_01.jpg",
            "tags": ["kyoto", "japan", "birthday", "cherry_blossoms", "travel"],
        },
        {
            "photo_id": "photo_002",
            "title": "Summer Beach Sunset with Alex",
            "tagged_friends": ["Alex"],
            "special_moment": "Annual Summer Reunion",
            "location": "Malibu, California",
            "storage_class": "COLDLINE",
            "gcs_uri": f"gs://{BUCKET_NAME}/summer/sunset_02.jpg",
            "public_url": f"https://storage.googleapis.com/{BUCKET_NAME}/summer/sunset_02.jpg",
            "tags": ["beach", "sunset", "malibu", "summer"],
        },
        {
            "photo_id": "photo_003",
            "title": "Mountain Hike Milestone with Sarah and Alex",
            "tagged_friends": ["Sarah", "Alex"],
            "special_moment": "Yosemite Half Dome Hike",
            "location": "Yosemite National Park, California",
            "storage_class": "STANDARD",
            "gcs_uri": f"gs://{BUCKET_NAME}/hiking/yosemite_03.jpg",
            "public_url": f"https://storage.googleapis.com/{BUCKET_NAME}/hiking/yosemite_03.jpg",
            "tags": ["yosemite", "hiking", "nature", "milestone"],
        },
    ]

    for item in seed_items:
        doc_ref = db.collection(COLLECTION_NAME).document(item["photo_id"])
        doc_ref.set(item)
        print(f"Seeded photo document: {item['photo_id']} - {item['title']}")

    print("Firestore seeding completed successfully!")


if __name__ == "__main__":
    seed_database()
