export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_ENDPOINTS = {
    DATASETS: {
        LIST: `${API_BASE_URL}/api/annotations/datasets/list`,
        CREATE: `${API_BASE_URL}/api/annotations/datasets/create`,
        DELETE: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}`,
        STATS: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/stats`,
        UPLOAD: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/upload`,
        EXPORT: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/export`,
        EXPORT_STATUS: (id, jobId) => `${API_BASE_URL}/api/annotations/datasets/${id}/export-status/${jobId}`,
        ANALYZE: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/analyze`,
        DOWNLOAD_FORMAT: (id, format) => `${API_BASE_URL}/api/annotations/datasets/${id}/download-format?format=${format}`,
        UPLOAD_VIDEO: (id) => `${API_BASE_URL}/api/annotations/datasets/${id}/upload-video`,
        MEMBERS: (id) => `${API_BASE_URL}/api/datasets/${id}/members`,
        MEMBER_REMOVE: (id, userId) => `${API_BASE_URL}/api/datasets/${id}/members/${userId}`,
        ACTIVITY: (id) => `${API_BASE_URL}/api/datasets/${id}/activity`,
    },
    ANNOTATIONS: {
        GET_IMAGE: (datasetId, filename) => `${API_BASE_URL}/api/annotations/image/${datasetId}/${filename}`,
        GET_ANNOTATION: (datasetId, imageId) => `${API_BASE_URL}/api/annotations/annotations/${datasetId}/${imageId}`,
        SAVE: `${API_BASE_URL}/api/annotations/save`,
        AUTO_LABEL: `${API_BASE_URL}/api/annotations/auto-label`,
        AUTO_LABEL_STATUS: (datasetId, jobId) => `${API_BASE_URL}/api/annotations/datasets/${datasetId}/auto-label-status/${jobId}`,
        UNCERTAINTY: (datasetId) => `${API_BASE_URL}/api/annotations/datasets/${datasetId}/uncertainty`,
        EXPORT_STATUS: (datasetId, jobId) => `${API_BASE_URL}/api/annotations/datasets/${datasetId}/export-status/${jobId}`,
        DOWNLOAD: (datasetId) => `${API_BASE_URL}/api/annotations/datasets/${datasetId}/download`,
    },
    TRAINING: {
        START: `${API_BASE_URL}/api/training/start`,
        START_FROM_DATASET: `${API_BASE_URL}/api/training/start-from-dataset`,
        START_MICRO: `${API_BASE_URL}/api/training/start-micro`,
        EXPORT_AND_TRAIN: `${API_BASE_URL}/api/training/export-and-train`,
        JOBS: `${API_BASE_URL}/api/training/jobs`,
        JOB: (id) => `${API_BASE_URL}/api/training/job/${id}`,
        JOB_METRICS: (id) => `${API_BASE_URL}/api/training/job/${id}/metrics`,
        TERMINATE: (id) => `${API_BASE_URL}/api/training/terminate/${id}`,
        PREVIEW_AUGMENTATION: `${API_BASE_URL}/api/training/preview-augmentation`,
    },
    SMART: {
        SEGMENT: `${API_BASE_URL}/api/smart/segment`,
    },
    MODELS: {
        LIST: `${API_BASE_URL}/api/models/list`,
        DELETE: (name) => `${API_BASE_URL}/api/models/delete/${name}`,
        DOWNLOAD: (name) => `${API_BASE_URL}/api/models/download/${name}`,
        EXPORT: (name, format) => `${API_BASE_URL}/api/models/export/${name}?format=${format}`,
        INFO: (name) => `${API_BASE_URL}/api/models/info/${name}`,
    },
    INFERENCE: {
        PREDICT: `${API_BASE_URL}/api/inference/predict`,
        LIST: `${API_BASE_URL}/api/inference/models`,
    },
    HEALTH: `${API_BASE_URL}/health`,
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
