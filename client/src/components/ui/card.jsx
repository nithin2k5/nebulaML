import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "relative border border-violet-500/30 bg-black/40 backdrop-blur-md rounded-none",
      className
    )}
    {...props}
  >
    <div className="absolute -top-[1px] -left-[1px] bg-violet-500/20 text-violet-400 border border-violet-500/50 text-[10px] font-mono font-bold px-2 py-0.5 flex items-center z-10 uppercase tracking-widest hidden group-hover:flex">
      MODULE_ACTIVE
    </div>
    <div className="absolute -top-1 -left-1 w-2 h-2 border-t border-l border-violet-500/50 pointer-events-none" />
    <div className="absolute -top-1 -right-1 w-2 h-2 border-t border-r border-violet-500/50 pointer-events-none" />
    <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b border-l border-violet-500/50 pointer-events-none" />
    <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b border-r border-violet-500/50 pointer-events-none" />
    {props.children}
  </div>
))
Card.displayName = "Card"

const CardHeader = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-6 border-b border-white/10", className)}
    {...props} />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("font-bold uppercase tracking-widest text-white flex items-center gap-2", className)}
    {...props} />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("text-xs font-mono text-gray-500 uppercase mt-2", className)}
    {...props} />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6", className)} {...props} />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center p-6 border-t border-white/10 bg-black/20", className)}
    {...props} />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }
