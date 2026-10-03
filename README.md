# NebulaML Platform

A self-hosted platform for the full object-detection lifecycle: upload, annotate,
version, train, evaluate, deploy and monitor — with YOLO, RT-DETR and torchvision
backends behind one workflow.

## 🚀 Features

- **Projects**: Each dataset is a project with its own images, annotations,
  versions, models and team
- **Annotation**: Manual bounding boxes, auto-labelling from an existing model,
  zero-shot and segment-assisted tools, and propagation across images
- **Dataset versioning**: Immutable snapshots with their own preprocessing and
  augmentation settings, so a training run is reproducible
- **Training**: YOLO, RT-DETR and torchvision backends, with preflight checks,
  a job queue, live metrics, confusion matrices and per-class breakdowns
- **Dataset health**: Class balance, duplicate and near-duplicate detection,
  blur and corruption checks, scored and tracked over time, plus
  embedding-space coverage gaps
- **Semantic search**: Find images by describing them ("a red truck at night"),
  find visually similar images, and detect duplicates that perceptual hashing
  misses — one CLIP index per project
- **Evaluation**: Score a run against a held-out split and browse its mistakes
  by kind (hallucinated, wrong class, loose box, duplicate, missed), with a
  confidence sweep and per-class diffs between runs
- **Label audit**: Uses a trained model to proofread the labels it was trained
  on — flagging wrong classes, missing boxes, empty boxes and loose extents,
  as a review queue with durable dismissals
- **Active learning**: Surfaces low-confidence predictions for review, spread
  across embedding clusters so a review batch is not forty frames of one
  scene, and can retrain automatically once enough new annotations land
- **Assistant**: An in-app assistant that reads your projects — labelling
  progress, dataset health, how a run scored and where it goes wrong
- **Live inference**: Point a webcam at the model over a WebSocket and watch
  it predict in real time, with latest-frame-wins so a slow model drops frames
  instead of falling behind
- **Monitoring**: Inference logging and drift detection per project
- **Collaboration**: Per-project roles (admin / annotator / viewer), email
  invitations and an activity log
- **Export**: YOLO, COCO and Pascal VOC, plus model export for deployment

## 🛠️ Tech Stack

### Client (Frontend)
- Next.js 15 (App Router)
- React 19
- Tailwind CSS
- shadcn/ui components (Radix primitives)
- Recharts, framer-motion, lucide-react

### Server (Backend)
- Python 3.9+
- FastAPI
- MySQL 8 (via mysql-connector, pooled)
- Ultralytics YOLO (YOLOv8), RT-DETR, torchvision
- PyTorch
- OpenCV, albumentations

## 📦 Installation

### Prerequisites
- Node.js 18+ and npm
- Python 3.9+
- pip

### Quick Start

1. Clone the repository:
```bash
git clone <repository-url>
cd NebulaML
```

2. Run the startup script:
```bash
chmod +x start.sh
./start.sh
```

This will:
- Set up Python virtual environment
- Install backend dependencies
- Install frontend dependencies
- Start both servers

### Manual Setup

#### Server Setup
```bash
cd server
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

The server will run on `http://localhost:8000`

#### Client Setup
```bash
cd client
npm install
npm run dev
```

The client will run on `http://localhost:3000`

## 📖 Usage

Sign-in is passwordless: enter your email and the server sends a one-time code.

Work happens inside a **project** (`/project/<id>`), whose tabs follow the
pipeline left to right. Each is also reachable directly via `?tab=<name>`.

1. **Upload** — drag in images, import a ZIP, or extract frames from a video
2. **Images** — browse, filter and delete what you uploaded, or search it
   by description once the CLIP index is built
3. **Annotate** — draw boxes by hand, or auto-label from an existing model and
   correct the results; `propagate` copies boxes across images, rescaled to
   each target's dimensions
4. **Health** — class balance, duplicates, blur and corruption, scored and
   tracked across snapshots; embedding coverage gaps; and a label audit that
   flags annotations a trained model confidently disagrees with
5. **Generate** — freeze a version with its own preprocessing and augmentation
   settings; training always runs against a version, not the live dataset
6. **Train** — pick a backend and version, run preflight, start the job.
   Progress, metrics, confusion matrix and per-class results stream live
7. **Evaluate** — score a run against the test split, browse its false
   positives and misses by kind, read the confidence sweep, and diff two runs
   per class
8. **Registry** — every version and run, with its metrics
9. **Test** — run the trained model against uploaded images, or stream your
   webcam to it and see live boxes with a real frames-per-second figure
10. **Deploy** — export the model (`pt`, `onnx`, `engine`, `coreml`) or call it
    through the API with an API key
11. **Active Learning** — review low-confidence predictions; optionally retrain
    automatically once enough new annotations accumulate
12. **Monitoring** — inference volume, confidence distribution and drift
13. **Team** — invite collaborators as admin, annotator or viewer

## 🎨 Theme

The platform features a sleek dark theme with violet accents:
- Background: Pure black (#000000)
- Primary: Violet (#a78bfa)
- Accent: Light violet
- All components use shadcn/ui for consistency

## 📁 Project Structure

```
NebulaML/
├── server/
│   ├── app/
│   │   ├── api/v1/endpoints/   # auth, annotations, training, inference,
│   │   │                       # models, active_learning, monitoring,
│   │   │                       # collaboration, smart_annotation, video,
│   │   │                       # chat, search, evaluation, label_audit,
│   │                       # stream
│   │   ├── core/               # config, rbac, access, logging, email, headers
│   │   ├── db/session.py       # schema, migrations, connection pool
│   │   └── services/           # trainers, inference, dataset analysis,
│   │                           # versioning, export, model registry,
│   │                           # embeddings, error_analysis,
│   │                           # assistant_tools, label_audit
│   ├── scripts/
│   ├── main.py
│   └── requirements.txt
├── client/
│   └── src/
│       ├── app/                # routes: home, dashboard, project/[id], annotate
│       ├── components/project/ # one component per project tab
│       ├── context/            # AuthContext
│       └── lib/                # config (endpoint map), usePolling, utils
├── tests/                      # unit suite (pytest)
└── start.sh
```

## 🔧 API Endpoints

Full interactive reference at `http://localhost:8000/docs`. Every route below
requires either a `Bearer` access token or an `X-API-Key` header.

| Prefix | Covers |
| --- | --- |
| `/api/auth` | OTP sign-in, refresh/rotate, profile, API keys, user admin |
| `/api/annotations` | Datasets, images, annotations, splits, export, image serving |
| `/api/training` | Jobs, queue, versions, preflight, metrics, auto-retrain config |
| `/api/inference` | Single and batch prediction, model listing |
| `/api/models` | List, info, download, export, delete |
| `/api/smart` | Segment-assisted and zero-shot annotation |
| `/api/active-learning` | Uncertainty collection, review, approve/reject |
| `/api/monitoring` | Inference logging, stats, drift |
| `/api/datasets` | Project members, invitations, activity log |
| `/api/video` | Frame extraction |
| `/api/chat` | In-app assistant (Claude, with read-only project tools) |
| `/api/search` | Semantic/visual search, embedding duplicates, clusters |
| `/api/evaluation` | Evaluate a run, browse per-image errors, compare runs |
| `/api/label-audit` | Flag suspect annotations, review queue, resolve findings |
| `/api/stream` | `ws://…/live` — live inference over a WebSocket |

A few of the most used:

- `POST /api/inference/predict` — run inference on a single image
- `GET  /api/training/jobs` — list training jobs
- `GET  /api/training/status/{job_id}` — poll one job
- `POST /api/training/start-from-dataset` — train from a dataset version
- `GET  /api/models/export/{model_name}?format=onnx` — export a trained model

## ⚙️ Optional configuration

Both additions below degrade gracefully — the platform runs without either.

| Variable | Default | Effect |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | unset | Enables the in-app assistant. Unset, `/api/chat` answers with a short canned reply and says it is unconfigured. |
| `ASSISTANT_MODEL` | `claude-opus-5` | Model backing the assistant. |
| `ASSISTANT_MAX_TOOL_ROUNDS` | `8` | Tool-calling rounds one question may take. Each round is an API call, so this is the per-question cost ceiling. |

Semantic search needs no key, but the CLIP weights (~600MB) download on first
use. With no network, indexing reports the feature as unavailable and the rest
of the platform is unaffected.

## 🧪 Development

```bash
make test         # unit suite
make test-integration   # needs a live MySQL
make lint         # ruff + eslint
make check        # format, lint, test
```

CI runs the backend lint gate and unit tests on Python 3.11, and lints and
builds the client on Node 20.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Ultralytics for YOLOv8
- shadcn/ui for beautiful components
- FastAPI for the backend framework

## Last Updated
- 2026-10-03
