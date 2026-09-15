import type { InjectionKey } from 'vue';
import type { useDesktopAgent } from '../useDesktopAgent';
export const APP_CONTEXT_KEY: InjectionKey<ReturnType<typeof useDesktopAgent>> = Symbol('desktop-agent');
