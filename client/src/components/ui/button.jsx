import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-none text-xs font-mono font-bold uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:border-violet-500 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-violet-500 text-black hover:bg-violet-400 border border-transparent",
        destructive:
          "bg-red-500 text-black hover:bg-red-400 border border-transparent",
        outline:
          "border border-white/20 bg-black text-white hover:border-violet-500 hover:text-violet-400",
        secondary:
          "bg-white/10 text-white hover:bg-white/20 border border-transparent",
        ghost: "hover:bg-violet-500/10 hover:text-violet-400 text-gray-400 border border-transparent",
        link: "text-violet-400 underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-[10px]",
        lg: "h-10 px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  )
})
Button.displayName = "Button"

export { Button, buttonVariants }
