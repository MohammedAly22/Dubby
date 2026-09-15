import { create } from 'zustand'

export type PlayerMode = 'original' | 'dub' | 'render'

interface PlayerState {
  video: HTMLVideoElement | null
  time: number
  duration: number
  playing: boolean
  stopAt: number | null
  mode: PlayerMode
  captions: boolean
  bgVolume: number
  follow: boolean

  setVideo: (v: HTMLVideoElement | null) => void
  setTime: (t: number) => void
  seek: (t: number, play?: boolean) => void
  playRange: (start: number, end: number) => void
  pause: () => void
  setMode: (m: PlayerMode) => void
  setCaptions: (c: boolean) => void
  setBgVolume: (v: number) => void
  setFollow: (f: boolean) => void
}

export const usePlayer = create<PlayerState>((set, get) => ({
  video: null,
  time: 0,
  duration: 0,
  playing: false,
  stopAt: null,
  mode: 'original',
  captions: true,
  bgVolume: 0.12,
  follow: true,

  setVideo: (video) => set({ video }),
  setTime: (t) => {
    if (Math.abs(t - get().time) >= 0.04) set({ time: t })
  },
  seek: (t, play = false) => {
    const v = get().video
    if (!v) return
    v.currentTime = Math.max(0, t)
    set({ time: t, stopAt: null })
    if (play) v.play().catch(() => {})
  },
  playRange: (start, end) => {
    const v = get().video
    if (!v) return
    v.currentTime = Math.max(0, start)
    set({ time: start, stopAt: end })
    v.play().catch(() => {})
  },
  pause: () => get().video?.pause(),
  setMode: (mode) => set({ mode }),
  setCaptions: (captions) => set({ captions }),
  setBgVolume: (bgVolume) => set({ bgVolume }),
  setFollow: (follow) => set({ follow }),
}))

// A single shared <audio> for previews so clips never overlap.
let previewAudio: HTMLAudioElement | null = null
export function playPreview(url: string, onEnd?: () => void): HTMLAudioElement {
  usePlayer.getState().pause()
  if (previewAudio) {
    previewAudio.pause()
    previewAudio.onended = null
  }
  previewAudio = new Audio(url)
  previewAudio.onended = () => onEnd?.()
  previewAudio.play().catch(() => {})
  return previewAudio
}
export function stopPreview() {
  previewAudio?.pause()
}
