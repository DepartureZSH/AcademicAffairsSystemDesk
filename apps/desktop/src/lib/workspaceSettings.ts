const WORKSPACE_PATH_KEY = "tech.karios.stt.desktop.workspacePath.v1";

export function savedWorkspacePath(): string | undefined {
  const value = window.localStorage.getItem(WORKSPACE_PATH_KEY)?.trim();
  return value || undefined;
}

export function saveWorkspacePath(path: string | undefined): void {
  if (path?.trim()) window.localStorage.setItem(WORKSPACE_PATH_KEY, path.trim());
  else window.localStorage.removeItem(WORKSPACE_PATH_KEY);
}
