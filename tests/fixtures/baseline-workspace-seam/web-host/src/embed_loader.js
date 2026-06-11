// Loads a remote frontend by env var — owner lives in a sibling repo.
const url = process.env.REMOTE_WIDGET_APP_URL;
export function loadWidget() {
  return import(/* @vite-ignore */ url);
}
