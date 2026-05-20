import { create } from "zustand";

export type ToolId =
  | "select"
  | "draw-room"
  | "place-window"
  | "place-door"
  | "erase";

export type SelectionTarget =
  | { kind: "space"; storyId: string; spaceId: string }
  | { kind: "edge"; storyId: string; edgeId: string }
  | { kind: "face"; storyId: string; faceId: string }
  | { kind: "window"; storyId: string; edgeId: string; windowDefId: string }
  | { kind: "door"; storyId: string; edgeId: string; doorDefId: string };

interface SelectionState {
  tool: ToolId;
  setTool: (t: ToolId) => void;

  selection: SelectionTarget | null;
  select: (s: SelectionTarget | null) => void;

  // chosen reusable definitions for placement tools
  activeWindowDefId: string | null;
  activeDoorDefId: string | null;
  setActiveWindowDefId: (id: string | null) => void;
  setActiveDoorDefId: (id: string | null) => void;

  // snap settings
  snapEnabled: boolean;
  setSnapEnabled: (v: boolean) => void;
  snapThresholdPx: number;
  setSnapThresholdPx: (v: number) => void;
}

export const useSelection = create<SelectionState>((set) => ({
  tool: "select",
  setTool: (tool) => set({ tool }),

  selection: null,
  select: (selection) => set({ selection }),

  activeWindowDefId: null,
  activeDoorDefId: null,
  setActiveWindowDefId: (id) => set({ activeWindowDefId: id }),
  setActiveDoorDefId: (id) => set({ activeDoorDefId: id }),

  snapEnabled: true,
  setSnapEnabled: (v) => set({ snapEnabled: v }),
  snapThresholdPx: 12,
  setSnapThresholdPx: (v) => set({ snapThresholdPx: v }),
}));
