import { useQuery, useMutation, type UseQueryOptions, type UseMutationOptions } from "@tanstack/react-query";
import { api, type ApiError } from "./api-client";

export function useApiGet<T>(
  key: string[],
  path: string | null,
  params?: Record<string, string>,
  options?: Omit<UseQueryOptions<T, ApiError, T, string[]>, "queryKey" | "queryFn">,
) {
  return useQuery<T, ApiError, T, string[]>({
    queryKey: key,
    queryFn: () => api.get<T>(path!),
    enabled: path !== null && (options?.enabled ?? true),
    ...options,
  });
}

export function useApiPost<TData, TResp>(
  path: string,
  options?: UseMutationOptions<TResp, ApiError, TData>,
) {
  return useMutation<TResp, ApiError, TData>({
    mutationFn: (data) => api.post<TResp>(path, data),
    ...options,
  });
}

export function useApiPatch<TData, TResp>(
  path: string,
  options?: UseMutationOptions<TResp, ApiError, TData>,
) {
  return useMutation<TResp, ApiError, TData>({
    mutationFn: (data) => api.patch<TResp>(path, data),
    ...options,
  });
}

export function useApiDelete<TResp = void>(
  path: string,
  options?: UseMutationOptions<TResp, ApiError, void>,
) {
  return useMutation<TResp, ApiError, void>({
    mutationFn: () => api.delete<TResp>(path),
    ...options,
  });
}
