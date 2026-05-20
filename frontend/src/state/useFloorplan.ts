import { create } from "zustand";
import { v4 as uuid } from "uuid";
import {
  type DoorDefinition,
  type DoorPlacement,
  type Floorplan,
  type Story,
  type Space,
  type ThermalZone,
  type WindowDefinition,
  type WindowPlacement,
  emptyFloorplan,
} from "../schema/types";
import { closePolygon, type DraftPoint } from "../drawing/geometryOps";

interface FloorplanState {
  doc: Floorplan;
  activeStoryId: string | null;

  // doc-level mutations
  load: (doc: Floorplan) => void;
  reset: () => void;

  // story
  addStory: (name?: string) => string;
  removeStory: (id: string) => void;
  setActiveStory: (id: string | null) => void;
  updateStory: (id: string, patch: Partial<Story>) => void;

  // space (face) creation via polygon close
  createSpaceFromPolygon: (storyId: string, points: DraftPoint[]) => string | null;
  removeSpace: (storyId: string, spaceId: string) => void;
  updateSpace: (storyId: string, spaceId: string, patch: Partial<Space>) => void;

  // thermal zones
  addThermalZone: (name?: string, color?: string) => string;
  removeThermalZone: (id: string) => void;
  updateThermalZone: (id: string, patch: Partial<ThermalZone>) => void;

  // window/door definitions
  addWindowDefinition: (patch?: Partial<WindowDefinition>) => string;
  removeWindowDefinition: (id: string) => void;
  updateWindowDefinition: (id: string, patch: Partial<WindowDefinition>) => void;

  addDoorDefinition: (patch?: Partial<DoorDefinition>) => string;
  removeDoorDefinition: (id: string) => void;
  updateDoorDefinition: (id: string, patch: Partial<DoorDefinition>) => void;

  // placements
  placeWindow: (storyId: string, placement: WindowPlacement) => void;
  removeWindow: (storyId: string, edgeId: string, windowDefId: string) => void;

  placeDoor: (storyId: string, placement: DoorPlacement) => void;
  removeDoor: (storyId: string, edgeId: string, doorDefId: string) => void;
}

const STORY_COLORS = ["#88B7D5", "#7FB069", "#F9A03F", "#D17B88", "#A18CD1"];

function newStory(name: string, color: string): Story {
  return {
    id: uuid(),
    handle: null,
    name,
    image_visible: true,
    below_floor_plenum_height: 0,
    floor_to_ceiling_height: 3.0,
    above_ceiling_plenum_height: 0,
    multiplier: 1,
    color,
    geometry: { id: uuid(), vertices: [], edges: [], faces: [] },
    images: [],
    spaces: [],
    shading: [],
    windows: [],
    doors: [],
  };
}

function ensureActive(state: FloorplanState): string | null {
  if (state.activeStoryId) return state.activeStoryId;
  return state.doc.stories[0]?.id ?? null;
}

export const useFloorplan = create<FloorplanState>((set) => ({
  doc: emptyFloorplan(),
  activeStoryId: null,

  load: (doc) =>
    set(() => ({
      doc,
      activeStoryId: doc.stories[0]?.id ?? null,
    })),

  reset: () =>
    set(() => ({
      doc: emptyFloorplan(),
      activeStoryId: null,
    })),

  addStory: (name) => {
    const id = uuid();
    set((state) => {
      const idx = state.doc.stories.length;
      const story = newStory(
        name ?? `Story ${idx + 1}`,
        STORY_COLORS[idx % STORY_COLORS.length],
      );
      story.id = id;
      return {
        doc: { ...state.doc, stories: [...state.doc.stories, story] },
        activeStoryId: id,
      };
    });
    return id;
  },

  removeStory: (id) =>
    set((state) => {
      const stories = state.doc.stories.filter((s) => s.id !== id);
      const activeStoryId =
        state.activeStoryId === id ? (stories[0]?.id ?? null) : state.activeStoryId;
      return { doc: { ...state.doc, stories }, activeStoryId };
    }),

  setActiveStory: (id) => set({ activeStoryId: id }),

  updateStory: (id, patch) =>
    set((state) => ({
      doc: {
        ...state.doc,
        stories: state.doc.stories.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      },
    })),

  createSpaceFromPolygon: (storyId, points) => {
    let createdSpaceId: string | null = null;
    set((state) => {
      const stories = state.doc.stories.map((story) => {
        if (story.id !== storyId) return story;
        const result = closePolygon(story.geometry, points);
        if (!result) return story;
        createdSpaceId = uuid();
        const space: Space = {
          id: createdSpaceId,
          handle: null,
          name: `Space ${story.spaces.length + 1}`,
          face_id: result.faceId,
          building_unit_id: null,
          thermal_zone_id: null,
          space_type_id: null,
          construction_set_id: null,
          pitched_roof_id: null,
          daylighting_controls: [],
          below_floor_plenum_height: null,
          floor_to_ceiling_height: null,
          above_ceiling_plenum_height: null,
          floor_offset: null,
          open_to_below: false,
          building_type_id: null,
          template: null,
        };
        return {
          ...story,
          geometry: result.geometry,
          spaces: [...story.spaces, space],
        };
      });
      return { doc: { ...state.doc, stories } };
    });
    return createdSpaceId;
  },

  removeSpace: (storyId, spaceId) =>
    set((state) => {
      const stories = state.doc.stories.map((story) => {
        if (story.id !== storyId) return story;
        const space = story.spaces.find((s) => s.id === spaceId);
        if (!space) return story;
        let geometry = story.geometry;
        if (space.face_id) {
          const face = geometry.faces.find((f) => f.id === space.face_id);
          const faces = geometry.faces.filter((f) => f.id !== space.face_id);
          const edges = geometry.edges
            .map((e) => ({
              ...e,
              face_ids: e.face_ids.filter((fid) => fid !== space.face_id),
            }))
            .filter((e) => e.face_ids.length > 0);
          const keptEdgeIds = new Set(edges.map((e) => e.id));
          const vertices = geometry.vertices
            .map((v) => ({
              ...v,
              edge_ids: v.edge_ids.filter((eid) => keptEdgeIds.has(eid)),
            }))
            .filter((v) => v.edge_ids.length > 0);
          // also drop any windows/doors that referenced removed edges
          const removedEdgeIds = new Set(
            face ? face.edge_ids.filter((eid) => !keptEdgeIds.has(eid)) : [],
          );
          const windows = story.windows.filter((w) => !removedEdgeIds.has(w.edge_id));
          const doors = story.doors.filter((d) => !removedEdgeIds.has(d.edge_id));
          geometry = { ...geometry, faces, edges, vertices };
          return {
            ...story,
            geometry,
            spaces: story.spaces.filter((s) => s.id !== spaceId),
            windows,
            doors,
          };
        }
        return { ...story, spaces: story.spaces.filter((s) => s.id !== spaceId) };
      });
      return { doc: { ...state.doc, stories } };
    }),

  updateSpace: (storyId, spaceId, patch) =>
    set((state) => ({
      doc: {
        ...state.doc,
        stories: state.doc.stories.map((s) =>
          s.id === storyId
            ? {
                ...s,
                spaces: s.spaces.map((sp) =>
                  sp.id === spaceId ? { ...sp, ...patch } : sp,
                ),
              }
            : s,
        ),
      },
    })),

  addThermalZone: (name, color) => {
    const id = uuid();
    set((state) => ({
      doc: {
        ...state.doc,
        thermal_zones: [
          ...state.doc.thermal_zones,
          {
            id,
            handle: null,
            name: name ?? `Thermal Zone ${state.doc.thermal_zones.length + 1}`,
            color: color ?? "#88B7D5",
          },
        ],
      },
    }));
    return id;
  },

  removeThermalZone: (id) =>
    set((state) => ({
      doc: {
        ...state.doc,
        thermal_zones: state.doc.thermal_zones.filter((z) => z.id !== id),
        stories: state.doc.stories.map((s) => ({
          ...s,
          spaces: s.spaces.map((sp) =>
            sp.thermal_zone_id === id ? { ...sp, thermal_zone_id: null } : sp,
          ),
        })),
      },
    })),

  updateThermalZone: (id, patch) =>
    set((state) => ({
      doc: {
        ...state.doc,
        thermal_zones: state.doc.thermal_zones.map((z) =>
          z.id === id ? { ...z, ...patch } : z,
        ),
      },
    })),

  addWindowDefinition: (patch) => {
    const id = uuid();
    set((state) => {
      const base: WindowDefinition = {
        id,
        name: `Window ${state.doc.window_definitions.length + 1}`,
        window_definition_mode: "Single Window",
        wwr: null,
        sill_height: 0.9,
        window_spacing: null,
        height: 1.2,
        width: 1.2,
        window_type: "Fixed",
        overhang_projection_factor: null,
        fin_projection_factor: null,
      };
      return {
        doc: {
          ...state.doc,
          window_definitions: [...state.doc.window_definitions, { ...base, ...patch, id }],
        },
      };
    });
    return id;
  },

  removeWindowDefinition: (id) =>
    set((state) => ({
      doc: {
        ...state.doc,
        window_definitions: state.doc.window_definitions.filter((w) => w.id !== id),
        stories: state.doc.stories.map((s) => ({
          ...s,
          windows: s.windows.filter((w) => w.window_definition_id !== id),
        })),
      },
    })),

  updateWindowDefinition: (id, patch) =>
    set((state) => ({
      doc: {
        ...state.doc,
        window_definitions: state.doc.window_definitions.map((w) =>
          w.id === id ? { ...w, ...patch } : w,
        ),
      },
    })),

  addDoorDefinition: (patch) => {
    const id = uuid();
    set((state) => {
      const base: DoorDefinition = {
        id,
        name: `Door ${state.doc.door_definitions.length + 1}`,
        width: 0.91,
        height: 2.03,
        door_type: "Door",
      };
      return {
        doc: {
          ...state.doc,
          door_definitions: [...state.doc.door_definitions, { ...base, ...patch, id }],
        },
      };
    });
    return id;
  },

  removeDoorDefinition: (id) =>
    set((state) => ({
      doc: {
        ...state.doc,
        door_definitions: state.doc.door_definitions.filter((d) => d.id !== id),
        stories: state.doc.stories.map((s) => ({
          ...s,
          doors: s.doors.filter((d) => d.door_definition_id !== id),
        })),
      },
    })),

  updateDoorDefinition: (id, patch) =>
    set((state) => ({
      doc: {
        ...state.doc,
        door_definitions: state.doc.door_definitions.map((d) =>
          d.id === id ? { ...d, ...patch } : d,
        ),
      },
    })),

  placeWindow: (storyId, placement) =>
    set((state) => ({
      doc: {
        ...state.doc,
        stories: state.doc.stories.map((s) =>
          s.id === storyId ? { ...s, windows: [...s.windows, placement] } : s,
        ),
      },
    })),

  removeWindow: (storyId, edgeId, windowDefId) =>
    set((state) => ({
      doc: {
        ...state.doc,
        stories: state.doc.stories.map((s) =>
          s.id === storyId
            ? {
                ...s,
                windows: s.windows.filter(
                  (w) =>
                    !(w.edge_id === edgeId && w.window_definition_id === windowDefId),
                ),
              }
            : s,
        ),
      },
    })),

  placeDoor: (storyId, placement) =>
    set((state) => ({
      doc: {
        ...state.doc,
        stories: state.doc.stories.map((s) =>
          s.id === storyId ? { ...s, doors: [...s.doors, placement] } : s,
        ),
      },
    })),

  removeDoor: (storyId, edgeId, doorDefId) =>
    set((state) => ({
      doc: {
        ...state.doc,
        stories: state.doc.stories.map((s) =>
          s.id === storyId
            ? {
                ...s,
                doors: s.doors.filter(
                  (d) => !(d.edge_id === edgeId && d.door_definition_id === doorDefId),
                ),
              }
            : s,
        ),
      },
    })),
}));

/** Convenience selector that returns the currently active Story (or null). */
export function useActiveStory(): Story | null {
  return useFloorplan((s) => {
    const id = ensureActive(s);
    return s.doc.stories.find((st) => st.id === id) ?? null;
  });
}
