import { useCallback, useEffect, useRef } from "react";

interface UseResizableOptions {
  /** Initial width in pixels */
  initial: number;
  /** Minimum width */
  min?: number;
  /** Maximum width */
  max?: number;
  /** Side being dragged ("left" means the panel is to the left of the divider) */
  side?: "left" | "right";
}

export function useResizable({
  initial,
  min = 160,
  max = 480,
  side = "left",
}: UseResizableOptions) {
  const widthRef = useRef(initial);
  const panelRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const updateWidth = useCallback(
    (w: number) => {
      const clamped = Math.max(min, Math.min(max, w));
      widthRef.current = clamped;
      if (panelRef.current) {
        panelRef.current.style.width = `${clamped}px`;
      }
      // Store in a data attribute on the body so CSS can react
      document.body.style.setProperty("--sidebar-width", `${clamped}px`);
    },
    [min, max],
  );

  useEffect(() => {
    // Set initial width
    updateWidth(initial);
  }, [initial, updateWidth]);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      e.preventDefault();
      updateWidth(side === "left" ? e.clientX : window.innerWidth - e.clientX);
    };

    const onMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [side, updateWidth]);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [],
  );

  return { panelRef, onMouseDown, getWidth: () => widthRef.current };
}
