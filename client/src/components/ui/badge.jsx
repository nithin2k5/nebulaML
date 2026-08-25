import * as React from "react"
import { cva } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-none border px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-widest transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500 hover:text-black",
        secondary:
          "border-transparent bg-white/10 text-white hover:bg-white/20 border border-white/20",
        destructive:
          "border-transparent bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500 hover:text-black",
        outline: "text-gray-400 border-white/20 hover:text-white hover:border-white/50",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}) {
  return (<div className={cn(badgeVariants({ variant }), className)} {...props} />)
}

export { Badge, badgeVariants }
