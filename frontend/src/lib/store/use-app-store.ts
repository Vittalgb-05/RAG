import { create } from "zustand";
import { Source } from "../api/types";

interface AppState {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;

  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;

  selectedSource: Source | null;
  setSelectedSource: (source: Source | null) => void;

  consentModalOpen: boolean;
  setConsentModalOpen: (open: boolean) => void;

  activeChatDocId: string | null;
  setActiveChatDocId: (docId: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  commandPaletteOpen: false,
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),

  selectedSource: null,
  setSelectedSource: (selectedSource) => set({ selectedSource }),

  consentModalOpen: false,
  setConsentModalOpen: (consentModalOpen) => set({ consentModalOpen }),

  activeChatDocId: null,
  setActiveChatDocId: (activeChatDocId) => set({ activeChatDocId }),
}));
