export {}
declare global {
  interface Window {
    localrepo?: {
      pickFolder: () => Promise<string | null>
      openExternal: (url: string) => Promise<void>
    }
  }
}
