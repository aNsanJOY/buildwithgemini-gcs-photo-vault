# Cloud Media & Memory Manager (GCS Photo Vault)

> A conversational AI agent built with Google ADK (Agent Development Kit) and deployed on Agent Engine that helps individuals organize, retrieve, and generate photo & video memories in Google Cloud Storage while remembering personal preferences across sessions.

---

## 🌟 Overview

**GCS Photo Vault** combines multi-modal AI generation, cloud storage orchestration, and cross-session memory tracking to provide an intelligent media manager. Users can query their photo memories, generate synthetic images and short videos, calculate storage cost savings across GCS tiers, upload local photos in bulk, and interact with a responsive glassmorphic chat interface.

---

## 🚀 Wired Features & Google Cloud Integrations

Based on the implemented codebase in `app/` and `agents-cli-manifest.yaml`, the agent leverages the following Google Cloud services and ADK tools:

### 1. 🧠 Long-Term Memory (Vertex AI Memory Bank)
- **`PreloadMemoryTool`**: Automatically injects past user facts, preferences, family/friend names, and media tags into the agent prompt context.
- **Session Extraction Callback**: Automatically submits conversation turns to Vertex AI Memory Bank (`add_session_to_memory`) at the end of each turn for cross-session retention.

### 2. 🗄️ Structured Media Storage & Search (Firestore)
- **Document Collection (`photo_memories`)**: Tracks media metadata including title, GCS URI, public HTTPS URL, storage class, tagged people/categories, special moments, uploader email, and upload timestamp.
- **Firestore Tools**:
  - `save_photo_memory`: Saves new photo memory records.
  - `get_photo_memory`: Fetches details for a specific photo ID.
  - `list_photo_memories`: Queries photo memory records filtered by tag or moment.

### 3. ☁️ Object Storage & Bulk Uploads (Google Cloud Storage)
- **Direct Byte Streaming**: Stores local user uploads, AI-generated images, and AI-generated videos directly in GCS buckets (`gs://...`).
- **Web Upload Endpoint**: `/upload` FastAPI endpoint supporting single and bulk file drag-and-drop uploads with custom tagging.

### 4. 🎨 Multi-Modal AI Media Generation
- **Image Generation (`generate_domain_image`)**:
  - Powered by `gemini-3.1-flash-lite-image` in the `global` region.
  - Saves raw generated image bytes as ADK artifacts (`tool_context.save_artifact`) for display in the ADK Playground and uploads them directly to GCS.
- **Video Generation (`generate_domain_video`)**:
  - Powered by Google's Omni model (`gemini-omni-flash-preview`) in the `global` region via Vertex AI Interactions API.
  - Saves raw generated video bytes as ADK artifacts and uploads MP4 files to GCS.

### 5. 🧮 Remote Code Execution (Agent Engine Sandbox)
- **`AgentEngineSandboxCodeExecutor`**: Executes Python code in a secure remote sandbox on Agent Engine to perform complex data calculations or analytical tasks.
- **Storage Tier Cost Calculator (`calculate_storage_cost_savings`)**: Calculates monthly storage costs and savings when transitioning photo libraries between `STANDARD`, `NEARLINE`, `COLDLINE`, and `ARCHIVE` classes.

### 6. 🌐 Public Domain Photo Discovery
- **`search_public_photos`**: Queries the Openverse API (`/v1/images/`) for free Creative Commons photos for visual reference or inspiration.

### 7. 🎛️ Interactive A2UI Cards (Agent-to-User Interface)
- **A2UI Schema Manager v0.8 & Basic Catalog**: Generates structured card surfaces (`Card`, `Column`, `Row`, `Text`, `Image`) rendered directly in the web UI.

### 8. 🔑 Google Auth & Glassmorphic Web Proxy
- **Google Identity Services (GIS)**: Google Sign-In widget in the web UI supporting user profile avatars, email display, and sign-out.
- **FastAPI Proxy (`main.py`)**: Communicates with the deployed Agent Runtime via the A2A (Agent-to-Agent) protocol over Application Default Credentials (ADC).
- **Rich UI**: Full-screen Lightbox with HTML5 video player, color-coded storage class badges, glassmorphic toast notifications, and quick action chips.

---

## 📋 Status of Planned Features

| Feature | Status | Notes |
|---|---|---|
| Cross-Session Memory Bank | ✅ Implemented | Wired via `PreloadMemoryTool` and callback |
| Firestore Metadata Store | ✅ Implemented | Document collection `photo_memories` |
| GCS Direct File Streaming | ✅ Implemented | Supports local uploads, AI images, and videos |
| Gemini AI Image Generation | ✅ Implemented | `gemini-3.1-flash-lite-image` |
| Gemini Omni AI Video Generation | ✅ Implemented | `gemini-omni-flash-preview` |
| Sandbox Code Executor | ✅ Implemented | `AgentEngineSandboxCodeExecutor` |
| Storage Cost Calculator | ✅ Implemented | `calculate_storage_cost_savings` |
| Openverse Public Photo Search | ✅ Implemented | `search_public_photos` |
| A2UI Rich Cards | ✅ Implemented | A2UI v0.8 renderer |
| Google Auth (GIS) & Bulk Upload | ✅ Implemented | Google Sign-In & `/upload` endpoint |
| Vertex AI RAG Engine | ⏳ Planned | Optional stretch goal; retrieval currently handled via Firestore & Openverse |

---

## 🛠️ Local Setup & Running Instructions

### Prerequisites
- Python 3.10+
- `gcloud` CLI logged into your GCP project with Application Default Credentials (`gcloud auth application-default login`)

### 1. Environment Configuration
Create a `.env` file or export the required environment variables:

```bash
export AGENT_ENGINE_RESOURCE_NAME="projects/YOUR_PROJECT_NUMBER/locations/us-east1/reasoningEngines/YOUR_REASONING_ENGINE_ID"
export AGENT_DIRECTORY="app"
```

### 2. Install Dependencies

```bash
# Install agent dependencies
pip install -r app/requirements.txt

# Install frontend proxy dependencies
pip install -r frontend/requirements.txt
```

### 3. Deploy Agent to Agent Engine

```bash
agents-cli deploy --project YOUR_PROJECT_ID --region us-east1
```

### 4. Run the Web Proxy & Chat Interface Locally

```bash
python frontend/main.py
```

Once running, navigate your web browser to the port printed in your terminal (default is port 8080) to access the GCS Photo Vault chat application.

---

## 📁 Repository Structure

```
.
├── app/
│   ├── agent.py                  # ADK Root Agent definition & callbacks
│   ├── a2ui_utils.py             # A2UI response formatter callback
│   └── tools/
│       ├── firestore_tools.py    # Firestore photo memory CRUD operations
│       ├── image_generation_tool.py  # Gemini Flash Lite image generation
│       ├── video_generation_tool.py  # Gemini Omni video generation
│       ├── storage_calculator_tool.py # GCS tier cost calculator
│       └── public_photo_tool.py  # Openverse public photo search API
├── frontend/
│   ├── main.py                   # FastAPI proxy talking A2A to Agent Engine
│   ├── requirements.txt          # Frontend dependencies
│   └── static/
│       └── index.html            # Single-page glassmorphic UI with A2UI & Google Auth
├── agents-cli-manifest.yaml       # Agent project deployment manifest
└── README.md
```
