export interface JarvisEvent<T = Record<string, unknown>> {
  type: string;
  payload: T;
  timestamp: string;
}
