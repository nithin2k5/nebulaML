"use client";

import React, { useState, useEffect } from 'react';
import { motion, useSpring, useMotionValue } from 'framer-motion';

export default function CustomCursor() {
  const [isHovering, setIsHovering] = useState(false);
  const [isClicking, setIsClicking] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [isPointerDevice, setIsPointerDevice] = useState(true);

  // Use motion values for better performance
  const mouseX = useMotionValue(-100);
  const mouseY = useMotionValue(-100);

  // Smooth springs for the outer ring
  const springConfig = { damping: 25, stiffness: 300, mass: 0.5 };
  const smoothX = useSpring(mouseX, springConfig);
  const smoothY = useSpring(mouseY, springConfig);

  useEffect(() => {
    // Only run on client and if pointer is fine
    if (window.matchMedia('(pointer: coarse)').matches) {
      setIsPointerDevice(false);
      return;
    }
    
    // Add a class to body so CSS can hide the default cursor
    document.body.classList.add('custom-cursor-active');

    const updateMousePosition = (e) => {
      if (!isVisible) setIsVisible(true);
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);
    };

    const handleMouseOver = (e) => {
      const target = e.target;
      
      // Check if we're hovering over a clickable element
      const isClickable = 
        target.tagName.toLowerCase() === 'a' ||
        target.tagName.toLowerCase() === 'button' ||
        target.tagName.toLowerCase() === 'input' ||
        target.tagName.toLowerCase() === 'select' ||
        target.tagName.toLowerCase() === 'textarea' ||
        target.closest('a') ||
        target.closest('button') ||
        target.closest('[role="button"]') ||
        target.closest('[role="tab"]') ||
        target.closest('[role="switch"]') ||
        target.closest('[role="checkbox"]') ||
        target.closest('.cursor-pointer');
        
      setIsHovering(!!isClickable);
    };

    const handleMouseDown = () => setIsClicking(true);
    const handleMouseUp = () => setIsClicking(false);
    
    const handleMouseLeave = () => setIsVisible(false);
    const handleMouseEnter = () => setIsVisible(true);

    window.addEventListener('mousemove', updateMousePosition);
    window.addEventListener('mouseover', handleMouseOver);
    window.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('mouseleave', handleMouseLeave);
    document.addEventListener('mouseenter', handleMouseEnter);

    return () => {
      document.body.classList.remove('custom-cursor-active');
      window.removeEventListener('mousemove', updateMousePosition);
      window.removeEventListener('mouseover', handleMouseOver);
      window.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('mouseleave', handleMouseLeave);
      document.removeEventListener('mouseenter', handleMouseEnter);
    };
  }, [mouseX, mouseY, isVisible]);

  if (!isPointerDevice) {
    return null;
  }

  return (
    <div className={`fixed inset-0 pointer-events-none z-[99999] transition-opacity duration-300 ${isVisible ? 'opacity-100' : 'opacity-0'}`}>
      {/* Outer Glow Ring */}
      <motion.div
        className="fixed top-0 left-0 rounded-full mix-blend-screen pointer-events-none"
        style={{
          x: smoothX,
          y: smoothY,
          translateX: '-50%',
          translateY: '-50%',
          width: isHovering ? 64 : 36,
          height: isHovering ? 64 : 36,
          border: isHovering ? '1px solid rgba(167, 139, 250, 0.8)' : '1px solid rgba(129, 140, 248, 0.4)',
          backgroundColor: isHovering ? 'rgba(167, 139, 250, 0.1)' : 'transparent',
          boxShadow: isHovering 
            ? '0 0 20px rgba(167, 139, 250, 0.4), inset 0 0 20px rgba(167, 139, 250, 0.2)' 
            : '0 0 10px rgba(129, 140, 248, 0.2)',
          scale: isClicking ? 0.8 : 1,
        }}
        transition={{ 
          width: { duration: 0.2 }, 
          height: { duration: 0.2 },
          backgroundColor: { duration: 0.2 },
          border: { duration: 0.2 }
        }}
      />
      
      {/* Inner Dot */}
      <motion.div
        className="fixed top-0 left-0 rounded-full bg-indigo-400 pointer-events-none"
        style={{
          x: mouseX,
          y: mouseY,
          translateX: '-50%',
          translateY: '-50%',
          width: isHovering ? 8 : 12,
          height: isHovering ? 8 : 12,
          boxShadow: '0 0 10px 2px rgba(129, 140, 248, 0.6)',
          opacity: isClicking ? 0.5 : 1,
          backgroundColor: isHovering ? '#a78bfa' : '#818cf8',
        }}
      />
    </div>
  );
}
