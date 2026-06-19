"use client"

import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"

import { cn } from "src/lib/utils"

function Checkbox({
  className,
  ...props
}: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer inline-flex size-4 shrink-0 cursor-pointer items-center justify-center rounded-[4px] border border-input bg-transparent transition-colors outline-none",
        "hover:border-ring",
        "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        "data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground",
        "data-disabled:pointer-events-none data-disabled:opacity-50",
        "data-invalid:border-destructive data-invalid:ring-3 data-invalid:ring-destructive/20",
        className
      )}
      {...props}
    />
  )
}

function CheckboxIndicator({
  className,
  ...props
}: CheckboxPrimitive.Indicator.Props) {
  return (
    <CheckboxPrimitive.Indicator
      data-slot="checkbox-indicator"
      className={cn(
        "flex items-center justify-center text-current",
        "data-closed:scale-0 data-closed:opacity-0",
        "data-open:scale-100 data-open:opacity-100",
        "transition-[opacity,transform] duration-150",
        className
      )}
      {...props}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    </CheckboxPrimitive.Indicator>
  )
}

export { Checkbox, CheckboxIndicator }
