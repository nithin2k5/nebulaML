export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_ENDPOINTS = {
    DATASETS: {
        LIST: `${API_BASE_URL}/api/annotations/datasets/list`,
        CREATE: `${API_BASE_URL}/api/annotations/datasets/create`,
        GET: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}`,
        STATS: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/stats`,
        UPLOAD: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/upload`,
        EXPORT: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/export`,
        ANALYZE: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/analyze`,
        DOWNLOAD_FORMAT: (id, format) => `${API_BASE_URL}/api/annotations/datasets/${id}/download-format?format=${format}`,
    },
    TRAINING: {
        START: `${API_BASE_URL}/api/training/start`,
        START_FROM_DATASET: `${API_BASE_URL}/api/training/start-from-dataset`,
        EXPORT_AND_TRAIN: `${API_BASE_URL}/api/training/export-and-train`,
        JOBS: `${API_BASE_URL}/api/training/jobs`,
        JOB: (id) => `${API_BASE_URL}/api/training/job/${id}`,
        PREVIEW_AUGMENTATION: `${API_BASE_URL}/api/training/preview-augmentation`,
    },
    INFERENCE: {
        PREDICT: `${API_BASE_URL}/api/inference/predict`,
    },
    MODELS: {
        LIST: `${API_BASE_URL}/api/inference/models`,
        EXPORT: (name, format) => `${API_BASE_URL}/api/models/export/${name}?format=${format}`,
        DOWNLOAD: (name) => `${API_BASE_URL}/api/models/download/${name}`,
        INFO: (name) => `${API_BASE_URL}/api/models/info/${name}`,
    },
    VIDEO: {
        EXTRACT_FRAMES: `${API_BASE_URL}/api/video/extract-frames`,
    },
    ACTIVE_LEARNING: {
        COLLECT: `${API_BASE_URL}/api/active-learning/collect`,
        UNCERTAIN: (datasetId) => `${API_BASE_URL}/api/active-learning/uncertain/${datasetId}`,
        APPROVE: `${API_BASE_URL}/api/active-learning/approve`,
    },
    MONITORING: {
        LOG: `${API_BASE_URL}/api/monitoring/log`,
        STATS: (datasetId) => `${API_BASE_URL}/api/monitoring/stats/${datasetId}`,
        DRIFT: (datasetId) => `${API_BASE_URL}/api/monitoring/drift/${datasetId}`,
    },
};
