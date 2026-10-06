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
  blur and corruption checks, scored and tracked over time
- **Evaluation**: Scores a finished model against a split through one shared
  metric path, so runs from different backends are comparable. Per-class
  table, class confusion, a full confusion matrix, a confidence sweep, and a
  per-image error browser that says *how* each box is wrong
- **Active learning**: Surfaces low-confidence predictions for review and can
  retrain automatically once enough new annotations land
- **Monitoring**: Inference logging and drift detection per project
- **Collaboration**: Per-project roles (admin / annotator / viewer), email
  invitations and an activity log
- **Export**: YOLO, COCO and Pascal VOC, plus model export for deployment
- **Publishing**: Share a frozen version on a public, revocable link
  (`/d/<slug>`) — a dataset card with classes, counts and samples, plus YOLO
  and COCO downloads. No account needed to view it; downloads can be turned
  off without taking the link down, and revoking is immediate and permanent

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
2. **Images** — browse, filter and delete what you uploaded
3. **Annotate** — draw boxes by hand, or auto-label from an existing model and
   correct the results; `propagate` copies boxes across images, rescaled to
   each target's dimensions
4. **Health** — class balance, duplicates, blur and corruption, scored and
   tracked across snapshots
5. **Generate** — freeze a version with its own preprocessing and augmentation
   settings; training always runs against a version, not the live dataset
6. **Train** — pick a backend and version, run preflight, start the job.
   Progress, metrics, confusion matrix and per-class results stream live
7. **Registry** — every version and run, with its metrics
8. **Evaluate** — score a finished model and browse what it got wrong. Every
   prediction is classed as hallucinated, wrong-class, loose-box, duplicate or
   missed, because the fixes differ; a confidence sweep says where to set the
   deployment threshold, and two runs can be diffed per class. Score against
   the current labels, or against a frozen version's snapshot — the data
   training actually consumed, which is the only ground truth that stays put.
   mAP is measured across the whole curve, so it does not move with the
   confidence setting; precision, recall and the error mix do
9. **Test** — run the trained model against new images or a webcam
10. **Deploy** — export the model (`pt`, `onnx`, `engine`, `coreml`) or call it
    through the API with an API key
11. **Active Learning** — review low-confidence predictions; optionally retrain
    automatically once enough new annotations accumulate
12. **Monitoring** — inference volume, confidence distribution and drift
13. **Publish** — put a frozen version on a public link anyone can open
    without an account. Admin only, since it exposes project data; the link is
    an unguessable token rather than the version id, the project's own name
    never leaves (only the title you choose), and revoking both kills the link
    and deletes the prepared downloads
14. **Team** — invite collaborators as admin, annotator or viewer

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
│   │   │                       # collaboration, smart_annotation, video, chat
│   │   ├── core/               # config, rbac, access, logging, email, headers
│   │   ├── db/session.py       # schema, migrations, connection pool
│   │   └── services/           # trainers, inference, dataset analysis,
│   │                           # versioning, export, model registry
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
requires either a `Bearer` access token or an `X-API-Key` header — except
`/api/public`, which is anonymous by design: the slug in the URL is the whole
credential, and those routes are rate limited per IP.

| Prefix | Covers |
| --- | --- |
| `/api/auth` | OTP sign-in, refresh/rotate, profile, API keys, user admin |
| `/api/annotations` | Datasets, images, annotations, splits, export, image serving |
| `/api/training` | Jobs, queue, versions, preflight, metrics, auto-retrain config |
| `/api/inference` | Single and batch prediction, model listing |
| `/api/models` | List, info, download, export, delete |
| `/api/smart` | Segment-assisted and zero-shot annotation |
| `/api/active-learning` | Uncertainty collection, review, approve/reject |
| `/api/evaluation` | Score a model on a split, error browser, confidence sweep, run diff |
| `/api/publish` | Publish a version, list links, edit a card, revoke |
| `/api/public` | **Unauthenticated.** Dataset card, previews and downloads by slug |
| `/api/monitoring` | Inference logging, stats, drift |
| `/api/datasets` | Project members, invitations, activity log |
| `/api/video` | Frame extraction |
| `/api/chat` | In-app assistant |

A few of the most used:

- `POST /api/inference/predict` — run inference on a single image
- `GET  /api/training/jobs` — list training jobs
- `GET  /api/training/status/{job_id}` — poll one job
- `POST /api/training/start-from-dataset` — train from a dataset version
- `GET  /api/models/export/{model_name}?format=onnx` — export a trained model
- `POST /api/publish` — publish a frozen version behind a public link
- `GET  /api/public/datasets/{slug}` — the public dataset card (no auth)

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
- 2026-09-25
