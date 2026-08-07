/**
 * TanStack Query hooks for user administration.
 * Replaces the fetch-in-useEffect + local useState pattern the Users page used.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usersApi } from "../api/resources/users";
import { queryKeys } from "../api/keys";
import type { CreateUserData, PaginatedResponse, User } from "../types";

export function useUsers(page = 1, perPage = 20) {
  return useQuery({
    queryKey: queryKeys.userList(page, perPage),
    queryFn: (): Promise<PaginatedResponse<User>> =>
      usersApi.list(page, perPage),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateUserData) => usersApi.create(data),
    onSuccess: () => {
      console.log("[useCreateUser] Created { invalidating: true }");
      queryClient.invalidateQueries({ queryKey: queryKeys.users() });
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => usersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users() });
    },
  });
}
