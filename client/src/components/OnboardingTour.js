"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { X, ChevronRight, ChevronLeft, Flag } from "lucide-react";
import { cn } from "@/lib/utils";

const TOUR_STEPS = [
  {
    targetId: "tour-dashboard",
    title: "Welcome to NebulaML 👋",
    content: "This is your command center. Monitor all your ML projects, API calls, and infrastructure health at a glance.",
    position: "right"
  },
  {
    targetId: "tour-datasets",
    title: "1. Datasets & Annotation",
    content: "Start your journey here. Create robust datasets, upload training images, and utilize our labeling tools to annotate your data points.",
    position: "right"
  },
  {
    targetId: "tour-training",
    title: "2. Model Training",
    content: "Once labeled, come here to select your architecture (like YOLOv8), configure hyperparameters, and launch cloud training jobs visually.",
    position: "right"
  },
  {
    targetId: "tour-inference",
    title: "3. Playground & Inference",
    content: "Test your freshly trained models on live data here before finally deploying them as scalable API endpoints.",
    position: "right"
  }
];

export default function OnboardingTour() {
  const [activeStep, setActiveStep] = useState(0);
  const [isVisible, setIsVisible] = useState(false);
  const [targetRect, setTargetRect] = useState(null);

  useEffect(() => {
    // Check if user already saw the tour
    const hasSeenTour = localStorage.getItem("nebulaml_tour_completed");
    if (!hasSeenTour) {
      // Small delay to let the UI render completely
      const timer = setTimeout(() => setIsVisible(true), 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    if (!isVisible) return;

    const updateRect = () => {
      const step = TOUR_STEPS[activeStep];
      const element = document.getElementById(step.targetId);
      if (element) {
        setTargetRect(element.getBoundingClientRect());
      } else {
        // Fallback to center if element not on screen
        setTargetRect(null);
      }
    };

    updateRect();
    window.addEventListener("resize", updateRect);
    window.addEventListener("scroll", updateRect, true);

    return () => {
      window.removeEventListener("resize", updateRect);
      window.removeEventListener("scroll", updateRect, true);
    };
  }, [activeStep, isVisible]);

  const handleClose = () => {
    setIsVisible(false);
    localStorage.setItem("nebulaml_tour_completed", "true");
  };

  const nextStep = () => {
    if (activeStep < TOUR_STEPS.length - 1) {
      setActiveStep(prev => prev + 1);
    } else {
      handleClose();
    }
  };

  const prevStep = () => {
    if (activeStep > 0) setActiveStep(prev => prev - 1);
  };

  if (!isVisible) return null;

  const step = TOUR_STEPS[activeStep];

  // Calculate tooltip position based on rect
  let tooltipStyle = {
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)"
  };

  let spotlightStyle = {};

  if (targetRect) {
    const padding = 8;
    spotlightStyle = {
      top: targetRect.top - padding,
      left: targetRect.left - padding,
      width: targetRect.width + padding * 2,
      height: targetRect.height + padding * 2,
    };

    // Position tooltip to the right of the element
    if (step.position === "right") {
      tooltipStyle = {
        top: Math.max(20, targetRect.top + targetRect.height / 2 - 100), // center vertically relative to target
        left: targetRect.right + 20,
      };
    }
  }

  return (
    <div className="fixed inset-0 z-[100] pointer-events-none">
      {/* Dark Backdrop */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-zinc-950/60 backdrop-blur-[2px] pointer-events-auto"
        onClick={handleClose}
      />

      {/* Spotlight Hollow - visually highlights the target element */}
      {targetRect && (
        <motion.div
          layout
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="absolute rounded-xl shadow-[0_0_0_9999px_rgba(3,3,3,0.7)] pointer-events-none z-[101]"
          style={spotlightStyle}
        />
      )}

      {/* Tooltip Card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeStep}
          initial={{ opacity: 0, y: 10, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.95 }}
          transition={{ duration: 0.2 }}
          className="absolute w-80 bg-[#111] border border-white/10 rounded-2xl shadow-2xl overflow-hidden pointer-events-auto z-[102]"
          style={tooltipStyle}
        >
          {/* Progress indicators */}
          <div className="flex h-1 bg-white/5 w-full">
            {TOUR_STEPS.map((_, i) => (
              <div 
                key={i} 
                className={cn(
                  "h-full flex-1 transition-all duration-300", 
                  i <= activeStep ? "bg-indigo-500" : "bg-transparent",
                  i > 0 && "border-l border-black/20"
                )} 
              />
            ))}
          </div>

          <div className="p-5">
            <div className="flex items-start justify-between mb-2">
              <h3 className="font-bold text-white text-lg flex items-center gap-2">
                {activeStep === 0 && <Flag className="w-4 h-4 text-indigo-400" />}
                {step.title}
              </h3>
              <button 
                onClick={handleClose}
                className="text-gray-500 hover:text-white transition-colors p-1 -mr-2 -mt-2 rounded-lg hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <p className="text-sm text-gray-400 leading-relaxed mb-6">
              {step.content}
            </p>

            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-gray-500 font-medium">
                Step {activeStep + 1} of {TOUR_STEPS.length}
              </p>
              
              <div className="flex items-center gap-2">
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={prevStep} 
                  disabled={activeStep === 0}
                  className="h-8 px-2 text-gray-400 hover:text-white disabled:opacity-30"
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <Button 
                  size="sm" 
                  onClick={nextStep}
                  className="h-8 bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20"
                >
                  {activeStep === TOUR_STEPS.length - 1 ? (
                    <>Done <Check className="w-4 h-4 ml-1.5" /></>
                  ) : (
                    <>Next <ChevronRight className="w-4 h-4 ml-1.5" /></>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
