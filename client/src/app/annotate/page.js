"use client";
// Force update

import { useState, useEffect, useRef, useCallback, Suspense, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import AutoLabelModal from "@/components/project/AutoLabelModal";
import { API_ENDPOINTS } from "@/lib/config";
import {
  Save, Trash2, Upload, ChevronLeft, ChevronRight, Home,
  Download, ZoomIn, ZoomOut, RotateCcw, Maximize, Check, Copy, Clipboard, Sparkles, Cpu
} from "lucide-react";

function AnnotationToolContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { token } = useAuth();
  const datasetId = searchParams.get('dataset');

  const [dataset, setDataset] = useState(null);
  const [images, setImages] = useState([]);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [boxes, setBoxes] = useState([]);
  const boxesRef = useRef([]);
  const isImageLoadingRef = useRef(true);
  const latestImageIndexRequested = useRef(currentImageIndex);
  const [boxHistory, setBoxHistory] = useState([]);
  const [selectedClass, setSelectedClass] = useState(0);
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [currentBox, setCurrentBox] = useState(null);
  const [selectedSplit, setSelectedSplit] = useState(null);
  const [stats, setStats] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [saveStatus, setSaveStatus] = useState(null); // 'saving' | 'saved' | 'error' | null
  const [reviewStatus, setReviewStatus] = useState('annotated'); // 'unlabeled' | 'predicted' | 'annotated' | 'reviewed'
  const [toastMessage, setToastMessage] = useState(null);
  const [showAutoLabel, setShowAutoLabel] = useState(false);
  const [copiedBoxes, setCopiedBoxes] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all'); // 'all', 'unlabeled', 'predicted', 'annotated', 'reviewed'
  const [annotationType, setAnnotationType] = useState('detection'); // 'detection' or 'classification'

  // Filter images based on status
  const filteredImages = useMemo(() => {
    return images.map((img, idx) => ({ ...img, originalIndex: idx }))
      .filter(img => {
        if (filterStatus === 'all') return true;
        const status = img.status || 'unlabeled';
        return status === filterStatus;
      });
  }, [images, filterStatus]);

  const getFilteredIndex = useCallback((originalIndex) => {
    return filteredImages.findIndex(img => img.originalIndex === originalIndex);
  }, [filteredImages]);

  const currentFilteredIndex = getFilteredIndex(currentImageIndex);

  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const fileInputRef = useRef(null);
  const containerRef = useRef(null);

  // Toast helper
  const showToast = useCallback((message, type = 'success') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 3000);
  }, []);

  // Initialization useEffect moved below fetchDataset to prevent ReferenceError (TDZ)

  const fetchStats = useCallback(async () => {
    if (!datasetId || !token) return;
    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.STATS(datasetId), {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (response.ok) setStats(await response.json());
    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  }, [datasetId, token]);

  useEffect(() => {
    if (!datasetId || !token) return;
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [datasetId, token, fetchStats]);

  useEffect(() => {
    if (images.length > 0 && currentImageIndex < images.length) {
      latestImageIndexRequested.current = currentImageIndex;
      loadImage(currentImageIndex);
      setZoom(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentImageIndex, images.length]);

  useEffect(() => {
    const handleResize = () => {
      const timeoutId = setTimeout(() => {
        if (canvasRef.current && imageRef.current?.complete) drawCanvas();
      }, 100);
      return () => clearTimeout(timeoutId);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxes, currentBox, isDrawing]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          handleNavigation('prev');
          break;
        case 'ArrowRight':
          e.preventDefault();
          handleNavigation('next');
          break;
        case 's':
        case 'S':
          e.preventDefault();
          handleSaveAnnotations().then(success => {
            if (success) showToast('Annotations saved!');
            else showToast('Failed to save', 'error');
          });
          break;
        case 'Delete':
        case 'Backspace':
          if (boxes.length > 0) {
            e.preventDefault();
            handleDeleteBox(boxes.length - 1);
            showToast('Last annotation deleted');
          }
          break;
        case 'z':
        case 'Z':
          if ((e.ctrlKey || e.metaKey) && boxHistory.length > 0) {
            e.preventDefault();
            const lastState = boxHistory[boxHistory.length - 1];
            boxesRef.current = lastState;
            setBoxes(lastState);
            setBoxHistory(prev => prev.slice(0, -1));
            showToast('Undo successful');
          }
          break;
        case 'c':
        case 'C':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            if (boxes.length > 0) {
              setCopiedBoxes(boxes);
              showToast(`Copied ${boxes.length} annotations`);
            }
          }
          break;
        case 'v':
        case 'V':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            if (copiedBoxes && copiedBoxes.length > 0) {
              setBoxHistory(prev => [...prev, boxesRef.current]);
              const newBoxes = [...boxesRef.current, ...copiedBoxes];
              boxesRef.current = newBoxes;
              setBoxes(newBoxes);
              showToast(`Pasted ${copiedBoxes.length} annotations`);
            }
          }
          break;
        default:
          // Number keys 1-9 for class selection
          const num = parseInt(e.key);
          if (num >= 1 && num <= 9 && dataset?.classes?.length >= num) {
            e.preventDefault();
            setSelectedClass(num - 1);
          }
          break;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxes, boxHistory, dataset, images, currentImageIndex, copiedBoxes]);

  const fetchDataset = useCallback(async () => {
    if (!datasetId || !token) return;
    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.GET(datasetId), {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`Failed to fetch dataset: ${response.status}`);
      const data = await response.json();
      setDataset(data);
      setImages(data.images || []);
    } catch (error) {
      console.error("Error fetching dataset:", error);
      showToast("Error loading dataset. Make sure backend is running.", 'error');
    }
  }, [datasetId, token, showToast]);

  useEffect(() => {
    if (datasetId) {
      fetchDataset();
      fetchStats();
    }
  }, [datasetId, fetchDataset, fetchStats]);

  const loadImage = useCallback(async (index) => {
    if (!images[index] || !datasetId || !token) return;

    // Instantly wipe old annotations synchronously so they don't ghost
    // over the new image while the network request is pending
    boxesRef.current = [];
    isImageLoadingRef.current = true;
    setBoxes([]);
    setBoxHistory([]);
    setReviewStatus('unlabeled');

    const img = images[index];
    try {
      const response = await fetch(API_ENDPOINTS.ANNOTATIONS.GET_ANNOTATION(datasetId, img.id), {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (latestImageIndexRequested.current !== index) return;
      if (response.ok) {
        const data = await response.json();
        const fetchedBoxes = data.boxes || [];
        boxesRef.current = fetchedBoxes;
        setBoxes(fetchedBoxes);
        setReviewStatus(data.status || 'annotated');
        setAnnotationType(data.annotation_type || (dataset?.type?.toLowerCase().includes('class') ? 'classification' : 'detection'));
      } else {
        boxesRef.current = [];
        setBoxes([]);
        setReviewStatus('unlabeled');
      }
    } catch (error) {
      if (latestImageIndexRequested.current === index) {
        boxesRef.current = [];
        setBoxes([]);
        setReviewStatus('unlabeled');
      }
    } finally {
      if (latestImageIndexRequested.current === index) {
        isImageLoadingRef.current = false;
      }
    }
    setSelectedSplit(img.split || null);
  }, [datasetId, images, token, dataset?.type]);

  const handleUploadImages = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;
    e.target.value = '';

    if (!datasetId) {
      showToast("Error: Dataset ID not found", 'error');
      return;
    }

    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'];
    const invalidFiles = files.filter(file => {
      const type = file.type.toLowerCase();
      return !validTypes.some(validType => type.includes(validType.split('/')[1]));
    });

    if (invalidFiles.length > 0) {
      showToast(`Invalid files: ${invalidFiles.map(f => f.name).join(', ')}`, 'error');
      return;
    }

    const formData = new FormData();
    files.forEach(file => formData.append("files", file));

    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.UPLOAD(datasetId), {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorData;
        try { errorData = JSON.parse(errorText); } catch { errorData = { detail: errorText || `Server error: ${response.status}` }; }
        throw new Error(errorData.detail || `Upload failed: ${response.status}`);
      }

      const data = await response.json();
      if (data.success) {
        showToast(`✅ ${data.uploaded} image${data.uploaded !== 1 ? 's' : ''} uploaded!`);
        fetchDataset();
      } else {
        throw new Error(data.detail || "Upload failed");
      }
    } catch (error) {
      showToast(`❌ Upload error: ${error.message}`, 'error');
    }
  };

  const getCanvasCoordinates = (e) => {
    const canvas = canvasRef.current;
    if (!canvas || !e) return { x: 0, y: 0 };
    const img = imageRef.current;
    if (!img || !img.complete || img.naturalWidth === 0) return { x: 0, y: 0 };

    const rect = canvas.getBoundingClientRect();
    const styles = window.getComputedStyle(canvas);
    const borderLeft = parseFloat(styles.borderLeftWidth) || 0;
    const borderTop = parseFloat(styles.borderTopWidth) || 0;
    const displayWidth = rect.width - (parseFloat(styles.borderLeftWidth) || 0) - (parseFloat(styles.borderRightWidth) || 0);
    const scale = img.naturalWidth / displayWidth;
    const mouseX = e.clientX - rect.left - borderLeft;
    const mouseY = e.clientY - rect.top - borderTop;
    const imageX = mouseX * scale;
    const imageY = mouseY * scale;
    return {
      x: Math.max(0, Math.min(imageX, img.naturalWidth)),
      y: Math.max(0, Math.min(imageY, img.naturalHeight))
    };
  };

  const [isSmartMode, setIsSmartMode] = useState(false);

  const handleMouseDown = async (e) => {
    e.preventDefault();
    if (!canvasRef.current || !dataset) return;
    const { x, y } = getCanvasCoordinates(e);

    if (isSmartMode) {
      // Smart Segment Logic
      if (!datasetId || !images[currentImageIndex]) return;

      const toastId = toast.loading("Segmenting...");
      try {
        const formData = new FormData();
        formData.append("dataset_id", datasetId);
        formData.append("image_id", images[currentImageIndex].id);

        // Send normalized coordinates
        const img = imageRef.current;
        formData.append("x", x / img.naturalWidth);
        formData.append("y", y / img.naturalHeight);

        const res = await fetch(API_ENDPOINTS.SMART.SEGMENT, {
          method: "POST",
          headers: { "Authorization": `Bearer ${token}` },
          body: formData
        });

        if (res.ok) {
          const data = await res.json();
          if (data.success && data.box) {
            // Add the smart box
            const newBox = {
              ...data.box,
              class_id: selectedClass,
              class_name: dataset.classes[selectedClass] || "object"
            };

            setBoxHistory(prev => [...prev, boxesRef.current]);
            const newBoxes = [...boxesRef.current, newBox];
            boxesRef.current = newBoxes;
            setBoxes(newBoxes);
            toast.dismiss(toastId);
            toast.success("Object segmented!");
          } else {
            toast.dismiss(toastId);
            toast.error("Could not segment object");
          }
        } else {
          throw new Error("Server error");
        }
      } catch (e) {
        console.error(e);
        toast.dismiss(toastId);
        toast.error("Smart segment failed");
      }
      return;
    }

    setIsDrawing(true);
    setStartPos({ x, y });
    setCurrentBox({ x, y, width: 0, height: 0, class_id: selectedClass });
  };

  const handleMouseMove = (e) => {
    e.preventDefault();
    if (!isDrawing || !startPos || !canvasRef.current) return;
    const { x, y } = getCanvasCoordinates(e);
    setCurrentBox({ x: startPos.x, y: startPos.y, width: x - startPos.x, height: y - startPos.y });
    drawCanvas();
  };

  const handleMouseUp = (e) => {
    e.preventDefault();
    if (!isDrawing || !startPos || !dataset || !canvasRef.current) {
      setIsDrawing(false); setStartPos(null); setCurrentBox(null);
      return;
    }

    const { x, y } = getCanvasCoordinates(e);
    const width = x - startPos.x;
    const height = y - startPos.y;

    if (Math.abs(width) > 10 && Math.abs(height) > 10) {
      // Safety check for class name
      const className = (dataset.classes && dataset.classes[selectedClass])
        ? dataset.classes[selectedClass]
        : `class_${selectedClass}`;

      const normalizedBox = {
        x: width < 0 ? startPos.x + width : startPos.x,
        y: height < 0 ? startPos.y + height : startPos.y,
        width: Math.abs(width),
        height: Math.abs(height),
        class_id: selectedClass,
        class_name: className
      };

      setBoxHistory(prev => [...prev, boxesRef.current]);
      const newBoxes = [...boxesRef.current, normalizedBox];
      boxesRef.current = newBoxes;
      setBoxes(newBoxes);
      setTimeout(() => { setCurrentBox(null); drawCanvas(); }, 0);
    } else {
      setCurrentBox(null);
      drawCanvas();
    }
    setIsDrawing(false);
    setStartPos(null);
  };

  // Color palette for classes
  const getClassColor = useCallback((classId) => {
    const colors = [
      { stroke: '#6366f1', fill: 'rgba(99,102,241,0.15)' },    // indigo
      { stroke: '#f43f5e', fill: 'rgba(244,63,94,0.15)' },     // rose
      { stroke: '#10b981', fill: 'rgba(16,185,129,0.15)' },    // emerald
      { stroke: '#f59e0b', fill: 'rgba(245,158,11,0.15)' },    // amber
      { stroke: '#8b5cf6', fill: 'rgba(139,92,246,0.15)' },    // violet
      { stroke: '#06b6d4', fill: 'rgba(6,182,212,0.15)' },     // cyan
      { stroke: '#ec4899', fill: 'rgba(236,72,153,0.15)' },    // pink
      { stroke: '#84cc16', fill: 'rgba(132,204,22,0.15)' },    // lime
      { stroke: '#ef4444', fill: 'rgba(239,68,68,0.15)' },     // red
      { stroke: '#3b82f6', fill: 'rgba(59,130,246,0.15)' },    // blue
    ];
    return colors[classId % colors.length];
  }, []);

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img || !img.complete || img.naturalWidth === 0) return;

    const ctx = canvas.getContext('2d');
    try {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Draw existing boxes with colored fills using the latest ref state
      boxesRef.current.forEach((box) => {
        const color = getClassColor(box.class_id);

        // Semi-transparent fill
        ctx.fillStyle = color.fill;
        ctx.fillRect(box.x, box.y, box.width, box.height);

        // Stroke
        ctx.strokeStyle = color.stroke;
        ctx.lineWidth = 3;
        ctx.strokeRect(box.x, box.y, box.width, box.height);

        // Label with background
        const labelText = `${box.class_name}`;
        ctx.font = 'bold 13px Inter, system-ui, sans-serif';
        const labelWidth = ctx.measureText(labelText).width + 12;
        const labelHeight = 22;

        // Label background
        ctx.fillStyle = color.stroke;
        const radius = 4;
        const lx = box.x;
        const ly = box.y - labelHeight;
        ctx.beginPath();
        ctx.moveTo(lx + radius, ly);
        ctx.lineTo(lx + labelWidth - radius, ly);
        ctx.quadraticCurveTo(lx + labelWidth, ly, lx + labelWidth, ly + radius);
        ctx.lineTo(lx + labelWidth, ly + labelHeight);
        ctx.lineTo(lx, ly + labelHeight);
        ctx.lineTo(lx, ly + radius);
        ctx.quadraticCurveTo(lx, ly, lx + radius, ly);
        ctx.closePath();
        ctx.fill();

        // Label text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(labelText, box.x + 6, box.y - 6);
      });

      // Draw current box being drawn
      if (currentBox && isDrawing) {
        ctx.strokeStyle = '#a78bfa';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.strokeRect(currentBox.x, currentBox.y, currentBox.width, currentBox.height);
        ctx.fillStyle = 'rgba(167, 139, 250, 0.1)';
        ctx.fillRect(currentBox.x, currentBox.y, currentBox.width, currentBox.height);
        ctx.setLineDash([]);
      }
    } catch (error) {
      console.error("Error drawing canvas:", error);
    }
  }, [currentBox, isDrawing, getClassColor]);

  useEffect(() => {
    if (canvasRef.current && imageRef.current?.complete) drawCanvas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxes, currentBox, isDrawing]);

  useEffect(() => {
    if (imageRef.current && imageRef.current.complete && canvasRef.current) drawCanvas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentImageIndex]);

  // Auto-save useEffect moved below handleSaveAnnotations to prevent ReferenceError (TDZ)
  
  const handleSaveAnnotations = useCallback(async (statusOverride = null) => {
    if (!images[currentImageIndex] || !dataset || !token) return false;

    // CRITICAL: If the image annotations are still loading from the API,
    // never auto-save since it would overwrite the DB with our temporary empty state!
    if (isImageLoadingRef.current) return false;

    setSaveStatus('saving');

    const naturalWidth = imageRef.current?.naturalWidth || 0;
    const naturalHeight = imageRef.current?.naturalHeight || 0;

    // Safety check: Don't save if dimensions are invalid (prevent div by zero in backend)
    if (naturalWidth === 0 || naturalHeight === 0) {
      console.warn("Cannot save annotations: Image dimensions not available");
      setSaveStatus(null);
      return false;
    }

    const img = images[currentImageIndex];

    // Determine status: if override provided use it, otherwise keep current status unless it was 'predicted'/'unlabeled' then promote to 'annotated'
    let newStatus = statusOverride || reviewStatus;
    const currentBoxesToSave = boxesRef.current;

    if (!statusOverride) {
      if (currentBoxesToSave.length > 0 && (reviewStatus === 'unlabeled' || reviewStatus === 'predicted')) {
        newStatus = 'annotated';
      } else if (currentBoxesToSave.length === 0) {
        newStatus = 'unlabeled';
      }
    }

    try {
      const response = await fetch(API_ENDPOINTS.ANNOTATIONS.SAVE, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          dataset_id: datasetId,
          image_id: img.id,
          image_name: img.filename,
          width: naturalWidth || 0,
          height: naturalHeight || 0,
          boxes: currentBoxesToSave,
          split: selectedSplit || null,
          status: newStatus,
          annotation_type: annotationType
        })
      });

      if (response.ok) {
        setSaveStatus('saved');
        setReviewStatus(newStatus);
        // Update the status of the current image in the images array
        setImages(prevImages => prevImages.map((image, idx) =>
          idx === currentImageIndex ? { ...image, status: newStatus } : image
        ));
        setTimeout(() => setSaveStatus(null), 2000);
        await fetchStats();
        return true;
      } else {
        setSaveStatus('error');
        setTimeout(() => setSaveStatus(null), 3000);
        return false;
      }
    } catch (error) {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus(null), 3000);
      return false;
    }
  }, [datasetId, images, currentImageIndex, dataset, token, reviewStatus, selectedSplit, annotationType, fetchStats]);

  // Auto-save when boxes change (debounced)
  useEffect(() => {
    if (boxes.length === 0 && reviewStatus === 'unlabeled') return; // Don't save empty if already unlabeled

    // Skip initial load
    if (saveStatus === 'saved' || saveStatus === 'loading') return;

    const timeoutId = setTimeout(() => {
      if (datasetId && images[currentImageIndex]) {
        handleSaveAnnotations();
      }
    }, 1000); // 1s debounce

    return () => clearTimeout(timeoutId);
  }, [boxes, datasetId, images, currentImageIndex, handleSaveAnnotations, reviewStatus, saveStatus]);

  const handleNavigation = async (direction) => {
    await handleSaveAnnotations();

    let nextInternalIndex = -1;

    if (direction === 'next') {
      if (currentFilteredIndex < filteredImages.length - 1) {
        nextInternalIndex = filteredImages[currentFilteredIndex + 1].originalIndex;
      }
    } else {
      if (currentFilteredIndex > 0) {
        nextInternalIndex = filteredImages[currentFilteredIndex - 1].originalIndex;
      }
    }

    if (nextInternalIndex !== -1) {
      setCurrentImageIndex(nextInternalIndex);
    }
  };

  const handleDeleteBox = (index) => {
    setBoxHistory(prev => [...prev, boxesRef.current]);
    const newBoxes = boxesRef.current.filter((_, i) => i !== index);
    boxesRef.current = newBoxes;
    setBoxes(newBoxes);
  };

  const handleZoom = (delta) => {
    setZoom(prev => Math.max(0.5, Math.min(3, prev + delta)));
  };

  // Calculate counts for filters
  const counts = images.reduce((acc, img) => {
    const status = img.status || 'unlabeled';
    acc[status] = (acc[status] || 0) + 1;
    acc.all = (acc.all || 0) + 1;
    return acc;
  }, { all: 0, unlabeled: 0, predicted: 0, annotated: 0, reviewed: 0 });

  if (!dataset) {
    return (
      <div className="min-h-screen bg-black text-foreground flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Loading dataset...</p>
        </div>
      </div>
    );
  }

  if (!dataset.classes || dataset.classes.length === 0) {
    return (
      <div className="min-h-screen bg-black text-foreground flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground mb-4">Error: Dataset has no classes defined</p>
          <Button onClick={() => router.push('/dashboard')} className="bg-primary hover:bg-primary/90">
            <Home className="mr-2" /> Return to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const currentImage = images[currentImageIndex];

  return (
    <div className="h-screen bg-black text-foreground overflow-hidden flex flex-col">
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`fixed top-4 right-4 z-[100] px-4 py-3 rounded-xl shadow-2xl text-sm font-medium animate-slide-up backdrop-blur-xl border ${toastMessage.type === 'error'
          ? 'bg-red-500/20 border-red-500/30 text-red-200'
          : 'bg-emerald-500/20 border-emerald-500/30 text-emerald-200'
          }`}>
          {toastMessage.message}
        </div>
      )}

      {/* Header */}
      <header className="border-b border-white/5 bg-zinc-950/90 backdrop-blur-xl shrink-0 z-50 h-[56px]">
        <div className="px-4 h-full">
          <div className="flex items-center justify-between h-full">
            <div className="flex items-center gap-3">
              <Button
                onClick={() => {
                  if (datasetId) router.push(`/project/${datasetId}`);
                  else router.push('/dashboard');
                }}
                variant="ghost"
                size="sm"
                className="text-gray-400 hover:text-white"
              >
                <ChevronLeft className="mr-1" />
                Back
              </Button>
              <div className="h-6 w-px bg-white/10" />
              <div>
                <h1 className="text-sm font-semibold">{dataset?.name || 'Loading...'}</h1>
                <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                  <span className={filterStatus !== 'all' ? 'text-indigo-400 font-medium' : ''}>
                    {currentFilteredIndex + 1} / {filteredImages.length}
                  </span>
                  {filterStatus !== 'all' && <span className="text-gray-600 text-[10px] uppercase">({filterStatus})</span>}
                  {selectedSplit && <span className="ml-1">• <span className="capitalize">{selectedSplit}</span></span>}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Save Status Indicator */}
              {saveStatus && (
                <Badge variant="outline" className={`text-xs ${saveStatus === 'saving' ? 'border-amber-500/30 text-amber-400' :
                  saveStatus === 'saved' ? 'border-emerald-500/30 text-emerald-400' :
                    'border-red-500/30 text-red-400'
                  }`}>
                  {saveStatus === 'saving' ? '● Saving...' : saveStatus === 'saved' ? '✓ Saved' : '✕ Error'}
                </Badge>
              )}

              {stats && (
                <Badge variant="outline" className="border-white/10 text-xs">
                  {stats.annotated_images || 0}/{stats.total_images || 0} done
                </Badge>
              )}
              <Badge className="bg-indigo-500/20 text-indigo-300 border-indigo-500/30 text-xs">
                {boxesRef.current.length} box{boxesRef.current.length !== 1 ? 'es' : ''}
              </Badge>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 min-h-0 overflow-hidden">
        <div className="grid grid-cols-[220px_1fr_220px] h-full">

          {/* Left Sidebar - Filters & Classes */}
          <div className="border-r border-white/5 bg-zinc-950/60 flex flex-col h-full">

            {/* Filter Section */}
            <div className="p-3 border-b border-white/5 space-y-3">
              <div>
                <h3 className="font-medium text-xs text-gray-500 uppercase tracking-wider mb-2 px-1">Filter Images</h3>
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger className="w-full h-8 text-xs bg-white/5 border-white/10">
                    <SelectValue placeholder="Filter status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">
                      <div className="flex items-center justify-between w-full min-w-[140px]">
                        <span>All Images</span>
                        <span className="text-xs text-muted-foreground ml-2">{counts.all}</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="unlabeled">
                      <div className="flex items-center justify-between w-full min-w-[140px]">
                        <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-gray-500" /> Unlabeled</span>
                        <span className="text-xs text-muted-foreground ml-2">{counts.unlabeled}</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="predicted">
                      <div className="flex items-center justify-between w-full min-w-[140px]">
                        <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-purple-500" /> Predicted</span>
                        <span className="text-xs text-muted-foreground ml-2">{counts.predicted}</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="annotated">
                      <div className="flex items-center justify-between w-full min-w-[140px]">
                        <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-indigo-500" /> Annotated</span>
                        <span className="text-xs text-muted-foreground ml-2">{counts.annotated}</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="reviewed">
                      <div className="flex items-center justify-between w-full min-w-[140px]">
                        <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Reviewed</span>
                        <span className="text-xs text-muted-foreground ml-2">{counts.reviewed}</span>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Quick Train Button */}
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full h-8 text-xs border-dashed border-white/20 hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-400 mb-2"
                  onClick={async () => {
                    if (!datasetId) return;
                    const toastId = toast.loading("Starting micro-training...");
                    try {
                      const formData = new FormData();
                      // dataset_yaml is handled by backend for existing datasets
                      formData.append("dataset_id", datasetId);
                      formData.append("model_name", "yolov8n.pt");
                      formData.append("epochs", "10"); // Micro training
                      formData.append("batch_size", "16");
                      formData.append("img_size", "416"); // Smaller for speed
                      formData.append("device", "cpu"); // Force CPU if needed or auto

                      // We need a way to tell backend to use existing dataset content
                      // For now, let's assume standard training endpoint handles 'dataset_id' 
                      // If not, we might need a specific/new endpoint or modify the existing one.
                      // Let's modify the existing start endpoint to accept dataset_id instead of yaml upload

                      const res = await fetch(API_ENDPOINTS.TRAINING.START_MICRO, {
                        method: "POST",
                        headers: { "Authorization": `Bearer ${token}` },
                        body: formData // Content-Type header specific for FormData not needed, browser sets it
                      });

                      if (res.ok) {
                        const data = await res.json();
                        toast.dismiss(toastId);
                        toast.success(`Micro-training started! (Job: ${data.job_id})`);
                      } else {
                        throw new Error("Failed to start");
                      }
                    } catch (e) {
                      console.error(e);
                      toast.dismiss(toastId);
                      toast.error("Failed to start micro-training");
                    }
                  }}
                >
                  <Cpu className="w-3 h-3 mr-1.5" />
                  Train Assistant (10 ep)
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  className="w-full h-8 text-xs border-dashed border-white/20 hover:border-indigo-500/50 hover:bg-indigo-500/10 hover:text-indigo-400"
                  onClick={async () => {
                    if (!datasetId) return;
                    const toastId = toast.loading("Analyzing dataset uncertainty...");
                    try {
                      // Fetch sorted images from backend
                      const res = await fetch(API_ENDPOINTS.ANNOTATIONS.UNCERTAINTY(datasetId), {
                        headers: { "Authorization": `Bearer ${token}` }
                      });
                      const data = await res.json();

                      if (data.success && data.images.length > 0) {
                        // Create a map of filename -> uncertainty score
                        const uncertaintyMap = new Map(data.images.map(img => [img.filename, img.uncertainty_score]));

                        // Sort current images based on the uncertainty map
                        // Images not in the map (labeled ones) go to the end
                        const sorted = [...images].sort((a, b) => {
                          const scoreA = uncertaintyMap.get(a.filename) ?? -1;
                          const scoreB = uncertaintyMap.get(b.filename) ?? -1;
                          return scoreB - scoreA; // Descending
                        });

                        setImages(sorted);
                        setCurrentImageIndex(0);
                        setFilterStatus('unlabeled'); // Switch to unlabeled to see the sorted ones
                        toast.dismiss(toastId);
                        toast.success(`Sorted by uncertainty! (${data.analyzed_count} images analyzed)`);
                      } else {
                        toast.dismiss(toastId);
                        toast.info("No unlabeled images to analyze");
                      }
                    } catch (e) {
                      console.error(e);
                      toast.dismiss(toastId);
                      toast.error("Failed to analyze uncertainty");
                    }
                  }}
                >
                  <Sparkles className="w-3 h-3 mr-1.5" />
                  Active Learning Sort
                </Button>
              </div>

              {/* Smart Mode Toggle */}
              <div className="pt-2 border-t border-white/5">
                <Button
                  variant={isSmartMode ? "default" : "outline"}
                  size="sm"
                  className={`w-full h-8 text-xs ${isSmartMode ? "bg-purple-600 hover:bg-purple-500 text-white border-transparent" : "border-dashed border-white/20 text-gray-400"}`}
                  onClick={() => setIsSmartMode(!isSmartMode)}
                >
                  <Sparkles className={`w-3 h-3 mr-1.5 ${isSmartMode ? "text-white" : "text-purple-400"}`} />
                  {isSmartMode ? "Smart Mode Active" : "Smart Mode Off"}
                </Button>
                <p className="text-[10px] text-gray-500 mt-1 text-center">
                  {isSmartMode ? "Click an object to auto-segment" : "Switch to Smart Mode for auto-segmentation"}
                </p>
              </div>

            </div>

            <div className="p-3 overflow-y-auto custom-scrollbar flex-1 space-y-4">
              {/* Annotation Mode Toggle */}
              <div>
                <h3 className="font-medium text-xs text-gray-500 uppercase tracking-wider mb-2 px-1">Mode</h3>
                <div className="flex bg-black/40 rounded-lg p-1 border border-white/5">
                  <button
                    onClick={() => setAnnotationType('detection')}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${annotationType === 'detection' ? 'bg-indigo-600 text-white shadow-sm' : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'}`}
                  >
                    Detection
                  </button>
                  <button
                    onClick={() => setAnnotationType('classification')}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${annotationType === 'classification' ? 'bg-emerald-600 text-white shadow-sm' : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'}`}
                  >
                    Classification
                  </button>
                </div>
              </div>

              <div>
                <h3 className="font-medium text-xs text-gray-500 uppercase tracking-wider mb-2 px-1">
                  {annotationType === 'classification' ? 'Assign Labels' : 'Classes'}
                </h3>
                {dataset?.classes?.map((cls, idx) => {
                  const color = getClassColor(idx);
                  const isAssigned = annotationType === 'classification' && boxes.some(b => b.class_name === cls);

                  return (
                    <button
                      key={idx}
                      onClick={() => {
                        setSelectedClass(idx);
                        if (annotationType === 'classification') {
                          // Toggle classification label
                          if (isAssigned) {
                            const newBoxes = boxes.filter(b => b.class_name !== cls);
                            boxesRef.current = newBoxes;
                            setBoxes(newBoxes);
                          } else {
                            // Provide dummy w/h coordinates to prevent errors in drawing/backend, even though backend ignores them
                            const newBox = { x: 50, y: 50, width: 200, height: 50, class_id: idx, class_name: cls };
                            const newBoxes = [...boxes, newBox];
                            boxesRef.current = newBoxes;
                            setBoxes(newBoxes);
                          }
                        }
                      }}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all flex items-center justify-between gap-2 mb-1 ${isAssigned
                          ? 'bg-emerald-500/20 border border-emerald-500/50 text-emerald-300'
                          : selectedClass === idx
                            ? 'bg-white/10 text-white border border-transparent'
                            : 'hover:bg-white/5 text-gray-400 hover:text-gray-200 border border-transparent'
                        }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: color.stroke }} />
                        <span className="truncate">{cls}</span>
                      </div>
                      <span className="text-[10px] text-gray-600 flex-shrink-0">{idx + 1}</span>
                    </button>
                  );
                })}
              </div>

              <div className="pt-3 border-t border-white/5">
                <h3 className="font-medium text-xs text-gray-500 uppercase tracking-wider mb-2 px-1">Shortcuts</h3>
                <div className="text-[11px] text-gray-500 space-y-1.5 px-1">
                  <div className="flex justify-between"><span>Navigate</span><kbd className="bg-white/5 px-1.5 py-0.5 rounded text-gray-400">← →</kbd></div>
                  <div className="flex justify-between"><span>Save</span><kbd className="bg-white/5 px-1.5 py-0.5 rounded text-gray-400">S</kbd></div>
                  <div className="flex justify-between"><span>Delete last</span><kbd className="bg-white/5 px-1.5 py-0.5 rounded text-gray-400">Del</kbd></div>
                  <div className="flex justify-between"><span>Undo</span><kbd className="bg-white/5 px-1.5 py-0.5 rounded text-gray-400">⌘Z</kbd></div>
                  <div className="flex justify-between"><span>Class</span><kbd className="bg-white/5 px-1.5 py-0.5 rounded text-gray-400">1-9</kbd></div>
                </div>
              </div>
            </div>
          </div>

          {/* Center - Canvas */}
          <div className="bg-zinc-900/50 relative flex flex-col h-full overflow-hidden">
            <div ref={containerRef} className="flex-1 flex items-center justify-center p-4 overflow-hidden relative">
              {currentImage ? (
                <div className="relative w-full h-full flex items-center justify-center" style={{ transform: `scale(${zoom})`, transition: 'transform 0.2s ease' }}>
                  <img
                    ref={imageRef}
                    src={API_ENDPOINTS.ANNOTATIONS.GET_IMAGE(datasetId, currentImage.filename)}
                    alt="Annotate"
                    className="hidden"
                    onLoad={(e) => {
                      const canvas = canvasRef.current;
                      const img = e.target;
                      if (canvas && img.complete && img.naturalWidth > 0) {
                        canvas.width = img.naturalWidth;
                        canvas.height = img.naturalHeight;
                        canvas.style.maxWidth = '100%';
                        canvas.style.maxHeight = '100%';
                        canvas.style.width = 'auto';
                        canvas.style.height = 'auto';
                        canvas.style.display = 'block';
                        canvas.offsetHeight;
                        setTimeout(() => drawCanvas(), 50);
                      }
                    }}
                    onError={(e) => console.error("Image failed:", e)}
                  />
                  <canvas
                    ref={canvasRef}
                    onMouseDown={(e) => {
                      if (annotationType === 'detection') handleMouseDown(e);
                    }}
                    onMouseMove={(e) => {
                      if (annotationType === 'detection') handleMouseMove(e);
                    }}
                    onMouseUp={(e) => {
                      if (annotationType === 'detection') handleMouseUp(e);
                    }}
                    onMouseLeave={() => {
                      if (annotationType === 'detection' && isDrawing && startPos) {
                        setIsDrawing(false); setStartPos(null); setCurrentBox(null);
                        setTimeout(() => drawCanvas(), 0);
                      }
                    }}
                    className={`border border-white/5 shadow-2xl rounded bg-black ${annotationType === 'detection' ? 'cursor-crosshair' : 'cursor-default pointer-events-none'}`}
                    style={{ maxWidth: '100%', maxHeight: '100%', display: 'block' }}
                  />
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-muted-foreground mb-4">
                    {filterStatus !== 'all' ? `No ${filterStatus} images found` : "No images available"}
                  </p>
                  <Button onClick={() => fileInputRef.current?.click()}>Upload Images</Button>
                  <Input ref={fileInputRef} type="file" multiple accept="image/*" onChange={handleUploadImages} className="hidden" />
                </div>
              )}
            </div>

            {/* Zoom Controls */}
            <div className="absolute bottom-20 right-4 flex flex-col gap-1 z-20">
              <Button variant="ghost" size="icon" onClick={() => handleZoom(0.25)} className="h-8 w-8 bg-black/60 backdrop-blur-sm border border-white/10 text-white hover:bg-white/10">
                <ZoomIn className="w-3.5 h-3.5" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => handleZoom(-0.25)} className="h-8 w-8 bg-black/60 backdrop-blur-sm border border-white/10 text-white hover:bg-white/10">
                <ZoomOut className="w-3.5 h-3.5" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setZoom(1)} className="h-8 w-8 bg-black/60 backdrop-blur-sm border border-white/10 text-white hover:bg-white/10">
                <Maximize className="w-3.5 h-3.5" />
              </Button>
            </div>

            {/* Bottom Navigation + Thumbnails */}
            {images.length > 0 && (
              <div className="border-t border-white/5 bg-zinc-950/80 backdrop-blur-sm shrink-0">
                {/* Thumbnail Strip (Filtered) */}
                <div className="h-16 flex items-center gap-1 px-4 overflow-x-auto custom-scrollbar">
                  {filteredImages.map((img, idx) => (
                    <div
                      key={img.id}
                      onClick={async () => {
                        await handleSaveAnnotations();
                        const originalIdx = img.originalIndex;
                        setCurrentImageIndex(originalIdx);
                      }}
                      className={`flex-shrink-0 w-12 h-12 rounded-lg overflow-hidden border-2 transition-all hover:opacity-100 relative ${img.originalIndex === currentImageIndex
                        ? 'border-indigo-500 opacity-100 scale-105'
                        : 'border-white/5 opacity-50 hover:border-white/20'
                        }`}
                    >
                      <img
                        src={API_ENDPOINTS.ANNOTATIONS.GET_IMAGE(datasetId, img.filename)}
                        alt={img.original_name}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                      {/* Status Dot */}
                      {img.status && img.status !== 'unlabeled' && (
                        <div className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ring-1 ring-black ${img.status === 'predicted' ? 'bg-purple-500' :
                          img.status === 'annotated' ? 'bg-indigo-500' :
                            img.status === 'reviewed' ? 'bg-emerald-500' : 'bg-gray-500'
                          }`} />
                      )}
                    </div>
                  ))}
                  {filteredImages.length === 0 && (
                    <div className="w-full text-center text-xs text-gray-500 py-4">
                      No images match filter &quot;{filterStatus}&quot;
                    </div>
                  )}
                </div>

                {/* Navigation */}
                <div className="h-10 flex items-center justify-between px-4 border-t border-white/5">
                  <Button
                    onClick={() => handleNavigation('prev')}
                    disabled={currentFilteredIndex <= 0}
                    variant="ghost" size="sm" className="h-7 text-xs text-gray-400"
                  >
                    <ChevronLeft className="mr-1" /> Prev
                  </Button>
                  <span className="text-xs text-gray-500 truncate max-w-[200px]">{currentImage?.original_name}</span>
                  <Button
                    onClick={() => handleNavigation('next')}
                    disabled={currentFilteredIndex >= filteredImages.length - 1}
                    variant="ghost" size="sm" className="h-7 text-xs text-gray-400"
                  >
                    Next <ChevronRight className="ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Right Sidebar - Annotations & Actions */}
          <div className="border-l border-white/5 bg-zinc-950/60 p-3 overflow-y-auto custom-scrollbar space-y-4">
            {/* Review Controls */}
            <div className="p-3 bg-white/5 rounded-lg border border-white/5 space-y-2 mb-4">
              <h3 className="font-medium text-xs text-gray-500 uppercase tracking-wider mb-2">Review</h3>
              <Button
                onClick={() => handleSaveAnnotations('reviewed')}
                className={`w-full h-8 text-xs ${reviewStatus === 'reviewed' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-white/10 hover:bg-white/20'}`}
              >
                <Check className="mr-1.5" />
                {reviewStatus === 'reviewed' ? 'Reviewed' : 'Mark as Reviewed'}
              </Button>
            </div>

            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 text-xs border border-white/5"
                  onClick={() => {
                    setCopiedBoxes(boxes);
                    showToast(`Copied ${boxes.length} boxes`);
                  }}
                >
                  <Copy className="mr-1.5" /> Copy
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 text-xs border border-white/5"
                  disabled={!copiedBoxes}
                  onClick={() => {
                    if (copiedBoxes) {
                      setBoxHistory(prev => [...prev, boxes]);
                      setBoxes(prev => [...prev, ...copiedBoxes]);
                      showToast(`Pasted ${copiedBoxes.length} boxes`);
                    }
                  }}
                >
                  <Clipboard className="mr-1.5" /> Paste
                </Button>
              </div>

              <Button onClick={async () => {
                const success = await handleSaveAnnotations();
                if (success) showToast("Annotations saved!");
                else showToast("Failed to save", 'error');
              }} className="w-full bg-indigo-600 hover:bg-indigo-500 h-9 text-sm">
                <Save className="mr-2 w-3.5 h-3.5" /> Save
              </Button>
              <Button
                onClick={() => setShowAutoLabel(true)}
                className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 h-9 text-sm border-0"
              >
                <Sparkles className="mr-2 w-3.5 h-3.5" /> Auto Label
              </Button>
              <Button
                onClick={async () => {
                  if (!datasetId) return;
                  await fetchStats();
                  window.location.href = API_ENDPOINTS.ANNOTATIONS.DOWNLOAD(datasetId);
                }}
                variant="outline"
                className="w-full border-white/10 h-9 text-sm"
              >
                <Download className="mr-2 w-3.5 h-3.5" /> Export
              </Button>
              {boxHistory.length > 0 && (
                <Button
                  onClick={() => {
                    const lastState = boxHistory[boxHistory.length - 1];
                    setBoxes(lastState);
                    setBoxHistory(prev => prev.slice(0, -1));
                    showToast('Undo successful');
                  }}
                  variant="ghost"
                  className="w-full border border-white/5 h-9 text-sm text-gray-400"
                >
                  <RotateCcw className="mr-2 w-3.5 h-3.5" /> Undo
                </Button>
              )}
            </div>

            {/* Annotations List */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-medium text-xs text-gray-500 uppercase tracking-wider">Annotations</h3>
                <Badge variant="outline" className="text-[10px] h-5 border-white/10">{boxes.length}</Badge>
              </div>

              <div className="space-y-1.5">
                {boxes.length > 0 ? (
                  boxes.map((box, index) => {
                    const color = getClassColor(box.class_id);
                    return (
                      <div key={index} className="flex items-center justify-between p-2 bg-white/[0.03] rounded-lg border border-white/5 hover:border-white/10 transition-colors group">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: color.stroke }} />
                            <span className="font-medium text-xs truncate">{box.class_name}</span>
                          </div>
                          <p className="text-[10px] text-gray-600 pl-4">
                            {Math.round(box.width)} × {Math.round(box.height)}
                          </p>
                        </div>
                        <Button
                          onClick={() => handleDeleteBox(index)}
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                    );
                  })
                ) : (
                  <div className="text-center py-6 border border-dashed border-white/5 rounded-lg">
                    <p className="text-xs text-gray-600">Draw boxes on the image</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
      <AutoLabelModal
        isOpen={showAutoLabel}
        onClose={() => setShowAutoLabel(false)}
        datasetId={datasetId}
        onComplete={() => {
          fetchStats();
          loadImage(currentImageIndex); // Reload current image if it was auto-labeled
        }}
      />
    </div>
  );
}

export default function AnnotatePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-black text-foreground flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Loading annotation tool...</p>
        </div>
      </div>
    }>
      <AnnotationToolContent />
    </Suspense>
  );
}
